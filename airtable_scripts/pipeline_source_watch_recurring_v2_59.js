/*
            V2.59.0 SOURCE-WATCH-DRIVEN REGISTRY-ROUTED PIPELINE MONITOR + MULTI-STATIC DOCUMENT ROUTING + QUEUE ROUTER

            Purpose
            -------
            Compare the structurally validated target company official pipeline snapshot against
            existing target-company Portfolio rows before any initial backfill or recurring monitoring.

            Delta classes
            -------------
            - NEW PROGRAMME
            - PHASE CHANGE
            - INDICATION / PROGRAMME CHANGE
            - SOURCE DISAPPEARANCE
            - NO CHANGE
            - LATER STAGE PRESERVED (verified Airtable state is ahead of R&D pipeline source)

            Required Airtable configuration
            -------------------------------
            Input:
            companyRecordId   = existing automation input (target company is safely resolved by name for this test)

            Secret:
            adapterApiKey     = existing Airtable secret

            Important
            ---------
            - Portfolio master data remains read-only. Material deltas may be written only to Intelligence Update Queue, and Source Watch operational metadata may be refreshed.
            - The adapter's structural validation is the source guardrail.
            - The historical 61-row target company snapshot is regression context only, not a permanent production count.
            - Absence from one pipeline refresh is never an automatic discontinuation.
            - Phase matching is not allowed to override asset/programme identity.
            */

            const VERSION = "V2.59.0 REGISTRY-ROUTED RECURRING PIPELINE DELTA ENGINE - STATIC XLSX/PDF + CONTROLLED QUEUE WRITES";
            const ADAPTER_BASE_URL = "https://pharma-pipeline-pdf-adapter.onrender.com";

            const cfg = input.config();
            const sourceWatchRecordId = String(cfg.sourceWatchRecordId || "").trim();

            if (!sourceWatchRecordId) {
                throw new Error(
                    "sourceWatchRecordId is blank. Map this input from the current Source Watch record in the repeating group."
                );
            }

            let adapterApiKey = "";
            try {
                if (typeof input.secret === "function") {
                    adapterApiKey = String(input.secret("adapterApiKey") || "");
                } else if (input.secret && input.secret.adapterApiKey) {
                    adapterApiKey = String(input.secret.adapterApiKey || "");
                }
            } catch (e) {
                throw new Error(`Unable to read Airtable secret adapterApiKey: ${e.message || e}`);
            }
            if (!adapterApiKey) throw new Error("Airtable secret adapterApiKey is blank or unavailable.");

            const companiesTable = base.getTable("Companies");
            const sourceWatchTable = base.getTable("Source Watch");
            const adaptersTable = base.getTable("Adapter Registry");
            const portfolioTable = base.getTable("Portfolio");
            const updateQueueTable = base.getTable("Intelligence Update Queue");

            function txt(v) {
                return v === null || v === undefined ? "" : String(v);
            }
            function clean(v) {
                return txt(v).replace(/\s+/g, " ").trim();
            }
            function norm(v) {
                return txt(v)
                    .toLowerCase()
                    .normalize("NFKD")
                    .replace(/[\u0300-\u036f]/g, "")
                    .replace(/[®™]/g, "")
                    // Some source extractions can render a trademark symbol as literal
                    // trailing letters. Normalise that only for identity matching.
                    .replace(/\b([a-z][a-z0-9]{3,})tm\b/g, "$1")
                    .replace(/[–—‑−]/g, "-")
                    .replace(/[^a-z0-9]+/g, " ")
                    .replace(/\s+/g, " ")
                    .trim();
            }
            function compact(v) {
                return norm(v).replace(/\s+/g, "");
            }
            function unique(arr) {
                return [...new Set((arr || []).filter(Boolean))];
            }
            function field(name) {
                try { return portfolioTable.getField(name); } catch (_) { return null; }
            }
            function cellText(record, f) {
                if (!f) return "";
                try { return clean(record.getCellValueAsString(f)); } catch (_) { return ""; }
            }
            function selectText(record, f) {
                if (!f) return "";
                const raw = record.getCellValue(f);
                if (raw && typeof raw === "object" && raw.name) return clean(raw.name);
                return cellText(record, f);
            }
            function linkNames(record, f) {
                if (!f) return [];
                const raw = record.getCellValue(f);
                if (!Array.isArray(raw)) return [];
                return raw.map(x => clean(x && x.name)).filter(Boolean);
            }
            function tokenSet(v, stop = new Set()) {
                return new Set(
                    norm(v).split(" ").filter(t => t && t.length > 1 && !stop.has(t))
                );
            }
            function similarity(a, b, stop = new Set()) {
                const A = tokenSet(a, stop);
                const B = tokenSet(b, stop);
                if (!A.size || !B.size) return 0;
                let inter = 0;
                for (const t of A) if (B.has(t)) inter++;
                const union = new Set([...A, ...B]).size;
                const containment = inter / Math.min(A.size, B.size);
                const jaccard = inter / union;
                return 0.7 * containment + 0.3 * jaccard;
            }

            const IND_STOP = new Set([
                "the","a","an","and","or","of","for","to","in","with","without","patients","patient",
                "adults","adult","children","pediatric","biologic","us","eu","orphan","fast","track",
                "prime","priority","review","study"
            ]);

            function normalizedIndication(v) {
                return norm(
                    txt(v)
                        .replace(/\bfirst[- ]line\b/gi, "1L")
                        .replace(/\bsecond[- ]line\b/gi, "2L")
                        .replace(/\bthird[- ]line\b/gi, "3L")
                        .replace(/\bnon[- ]small cell lung cancer\b/gi, "NSCLC")
                        .replace(/\bchronic weight management\b/gi, "obesity weight management")
                        .replace(/\bcastration resistant\b/gi, "CRPC")
                        .replace(/\bcastration sensitive\b/gi, "CSPC")
                );
            }
            function indicationSimilarity(a, b) {
                return similarity(normalizedIndication(a), normalizedIndication(b), IND_STOP);
            }

            function extractCodes(v) {
                const raw = txt(v).toUpperCase().replace(/[–—‑−]/g, "-");
                const patterns = [
                    /\bPF-\s?\d{5,9}\b/g,
                    /\bMET-\s?\d{2,5}I\b/g,
                    /\bVLA\s?\d{2,5}\b/g,
                    /\bSAR[- ]?\d{4,9}\b/g,
                    /\bSP[- ]?\d{4,9}\b/g
                ];
                let out = [];
                for (const p of patterns) out = out.concat(raw.match(p) || []);
                return unique(out.map(x => x.replace(/\s+/g, "")));
            }

            function sourceIdentityParts(row) {
                const a = clean(row.asset);
                const parts = [a, row.developmentCode];
                const beforeParen = clean(a.split("(")[0]);
                if (beforeParen) parts.push(beforeParen);

                const paren = /\(([^)]+)\)/g;
                let m;
                while ((m = paren.exec(a)) !== null) parts.push(clean(m[1]));

                for (const p of a.split(/\+|\//g)) parts.push(clean(p.replace(/[()]/g, " ")));
                return unique(parts.map(norm).filter(Boolean));
            }
            function existingIdentityParts(record, f) {
                const values = [
                    cellText(record, f.brand),
                    cellText(record, f.molecule),
                    cellText(record, f.devCode),
                    cellText(record, f.aliases)
                ];
                const parts = [];
                for (const v of values) {
                    if (!v) continue;
                    parts.push(v);
                    for (const p of v.split(/\+|\/|;|\n/g)) parts.push(p);
                }
                return unique(parts.map(norm).filter(Boolean));
            }
            function identityEvidence(sourceRow, record, f) {
                const sourceParts = sourceIdentityParts(sourceRow);
                const existingParts = existingIdentityParts(record, f);

                const sCodes = new Set(unique([
                    ...extractCodes(sourceRow.asset),
                    ...extractCodes(sourceRow.developmentCode)
                ]).map(compact));

                const eCodes = new Set(unique([
                    ...extractCodes(cellText(record, f.brand)),
                    ...extractCodes(cellText(record, f.molecule)),
                    ...extractCodes(cellText(record, f.devCode)),
                    ...extractCodes(cellText(record, f.aliases))
                ]).map(compact));

                const sharedCodes = [...sCodes].filter(c => eCodes.has(c));
                let exactIdentity = false;
                let exactPartIdentity = false;
                let bestSimilarity = 0;

                for (const s of sourceParts) {
                    for (const e of existingParts) {
                        if (!s || !e) continue;

                        // Exact component identity matters when an existing Brand / Asset
                        // contains multiple recognised names, e.g.
                        // "Fluzone HD / Efluelda", while the source publishes "Fluzone HD".
                        if (s === e) {
                            exactPartIdentity = true;
                            exactIdentity = true;
                        } else if (
                            (s.length >= 5 && e.includes(s)) ||
                            (e.length >= 5 && s.includes(e))
                        ) {
                            exactIdentity = true;
                        }

                        bestSimilarity = Math.max(bestSimilarity, similarity(s, e));
                    }
                }

                return {
                    sharedCodes,
                    codeMatch: sharedCodes.length > 0,
                    exactIdentity,
                    exactPartIdentity,
                    identitySimilarity: bestSimilarity
                };
            }

            function sourceWholeIdentityCandidates(row) {
                const raw = clean(row.asset);
                const noParen = clean(raw.replace(/\([^)]*\)/g, " "));
                const values = [raw, noParen, row.developmentCode];
                return unique(values.map(norm).filter(Boolean));
            }
            function existingWholeIdentityCandidates(record, f) {
                const values = [
                    cellText(record, f.brand),
                    cellText(record, f.molecule),
                    cellText(record, f.devCode)
                ];

                const aliases = cellText(record, f.aliases);
                if (aliases) {
                    for (const a of aliases.split(/\n|;|,/g)) values.push(clean(a));
                }

                return unique(values.map(norm).filter(Boolean));
            }
            function wholeIdentityEvidence(sourceRow, record, f) {
                const sourceWhole = sourceWholeIdentityCandidates(sourceRow);
                const existingWhole = existingWholeIdentityCandidates(record, f);

                let exactWholeIdentity = false;
                let wholeIdentitySimilarity = 0;

                for (const a of sourceWhole) {
                    for (const b of existingWhole) {
                        if (!a || !b) continue;
                        if (a === b) exactWholeIdentity = true;
                        wholeIdentitySimilarity = Math.max(
                            wholeIdentitySimilarity,
                            similarity(a, b)
                        );
                    }
                }

                const sourceCodes = unique([
                    ...extractCodes(sourceRow.asset),
                    ...extractCodes(sourceRow.developmentCode)
                ]).map(compact);

                const existingCodes = unique([
                    ...extractCodes(cellText(record, f.brand)),
                    ...extractCodes(cellText(record, f.molecule)),
                    ...extractCodes(cellText(record, f.devCode)),
                    ...extractCodes(cellText(record, f.aliases))
                ]).map(compact);

                const sharedCodes = sourceCodes.filter(c => existingCodes.includes(c));

                return {
                    exactWholeIdentity,
                    wholeIdentitySimilarity,
                    sourceCodes,
                    existingCodes,
                    sharedCodes,
                    sourceCodeCoverage: sourceCodes.length ? sharedCodes.length / sourceCodes.length : 0,
                    existingCodeCoverage: existingCodes.length ? sharedCodes.length / existingCodes.length : 0
                };
            }

            function hasStrongIdentity(pair) {
                if (!pair) return false;
                if (pair.prog.programmeMatch) return true;
                if (pair.whole.exactWholeIdentity) return true;

                if (
                    pair.id.codeMatch &&
                    pair.whole.wholeIdentitySimilarity >= 0.60 &&
                    pair.whole.sourceCodeCoverage >= 0.50
                ) return true;

                if (
                    pair.id.exactIdentity &&
                    pair.whole.wholeIdentitySimilarity >= 0.72
                ) return true;

                return false;
            }

            function hasAnyIdentity(pair) {
                if (!pair) return false;
                return Boolean(
                    pair.prog.programmeMatch ||
                    pair.whole.exactWholeIdentity ||
                    pair.id.codeMatch ||
                    (
                        pair.id.exactIdentity &&
                        pair.whole.wholeIdentitySimilarity >= 0.45
                    )
                );
            }

            /* ------------------------------------------------------------
               Study / programme acronym extraction
               ------------------------------------------------------------ */

            function programmeTokensFromSource(indication) {
                const raw = txt(indication).replace(/[–—‑−]/g, "-");
                const tokens = [];

                // Parenthetical groups often contain the study/programme label.
                const paren = /\(([^)]+)\)/g;
                let m;
                while ((m = paren.exec(raw)) !== null) {
                    const group = clean(m[1]);
                    if (!group) continue;

                    // Ignore regulatory / descriptive groups.
                    if (/^(biologic|orphan|fast track|prime|priority review|rpd)/i.test(group)) continue;

                    // Capture labels containing a digit, e.g. MM-5, MEVPRO-1,
                    // Be6A LUNG-02, FourLight-3, HER2CLIMB-05, DV-001.
                    if (/[A-Za-z]/.test(group) && /\d/.test(group)) {
                        tokens.push(compact(group));
                    }
                }

                // Also detect common label shapes outside parentheses.
                const common = raw.match(
                    /\b(?:MM|MEVPRO|FOURLIGHT|HER2CLIMB|TALAPRO|KATSIS|DV|EV|TV|VALOR|MOUNTAINEER|SYMBIOTIC[- A-Z0-9]*|BE6A\s*LUNG|PADL1NK)[- A-Z0-9]*\d+\b/gi
                ) || [];

                for (const x of common) tokens.push(compact(x));

                return unique(tokens.filter(t => t.length >= 3));
            }
            function programmeTokensFromExisting(record, f) {
                const names = linkNames(record, f.clinicalTrials);
                const out = [];

                // 1) Linked trial/study identity remains the strongest programme evidence.
                for (const name of names) {
                    // Remove NCT number and retain study/acronym display text.
                    const cleaned = name.replace(/\bNCT\d+\b/gi, " ");
                    const pieces = cleaned.split(/[|/;,]/g).map(clean).filter(Boolean);
                    for (const p of pieces) out.push(compact(p));
                    out.push(compact(cleaned));
                }

                // 2) Programme-grain Portfolio rows created from the official pipeline may
                // carry the study/programme label in the source-facing Indication even when
                // no Clinical Trial is linked yet. Example: MEVPRO-1 / -2 / -3.
                //
                // Without this, three already-granular Mevrometostat rows are falsely
                // interpreted as one broad asset needing another split.
                const indicationTokens = programmeTokensFromSource(
                    cellText(record, f.indication)
                );
                for (const t of indicationTokens) out.push(t);

                return unique(out.filter(t => t.length >= 3));
            }
            function programmeMatchEvidence(sourceRow, record, f) {
                const sourceTokens = programmeTokensFromSource(sourceRow.indication);
                const existingTokens = programmeTokensFromExisting(record, f);

                const matches = [];
                for (const s of sourceTokens) {
                    for (const e of existingTokens) {
                        if (!s || !e) continue;
                        if (s === e || e.includes(s) || s.includes(e)) {
                            matches.push({source: s, existing: e});
                        }
                    }
                }

                return {
                    sourceTokens,
                    existingTokens,
                    matches,
                    programmeMatch: matches.length > 0
                };
            }

            /* ------------------------------------------------------------
               Clinical qualifier extraction: line/setting/segment
               ------------------------------------------------------------ */

            function qualifierSet(v) {
                const s = norm(v)
                    .replace(/\bfirst line\b/g, "1l")
                    .replace(/\bsecond line\b/g, "2l")
                    .replace(/\bthird line\b/g, "3l");

                const q = new Set();

                const tests = [
                    ["1l", /\b1l\b|\b1\/2l\b/],
                    ["2l", /\b2l\b|\b2l\+\b|\b1\/2l\b|\b2l\/3l\b/],
                    ["3l", /\b3l\b|\b3l\+\b|\b2l\/3l\b/],
                    ["maintenance", /\bmaintenance\b/],
                    ["post-transplant", /\bpost transplant\b|\bafter autologous stem cell transplantation\b/],
                    ["transplant-ineligible", /\btransplant ineligible\b/],
                    ["relapsed-refractory", /\brelapsed\b|\brefractory\b|\brrmm\b/],
                    ["adjuvant", /\badjuvant\b/],
                    ["neoadjuvant", /\bneoadjuvant\b/],
                    ["metastatic", /\bmetastatic\b/],
                    ["early", /\bearly\b/],
                    ["squamous", /\bsquamous\b/],
                    ["non-squamous", /\bnon squamous\b/],
                    ["cspc", /\bcspc\b|\bcastration sensitive\b/],
                    ["crpc", /\bcrpc\b|\bcastration resistant\b/],
                    ["post-cd38", /\bpost cd38\b|\bdaratumumab\b/],
                    ["double-class-exposed", /\bdouble class exposed\b/],
                ];

                for (const [label, re] of tests) if (re.test(s)) q.add(label);
                return q;
            }
            function qualifierEvidence(sourceRow, record, f) {
                const sourceQ = qualifierSet(sourceRow.indication);
                const existingQ = qualifierSet([
                    cellText(record, f.indication),
                    cellText(record, f.setting),
                    cellText(record, f.segment),
                    cellText(record, f.subtype)
                ].join(" "));

                const shared = [...sourceQ].filter(x => existingQ.has(x));

                const lineLabels = new Set(["1l","2l","3l"]);
                const sourceLines = [...sourceQ].filter(x => lineLabels.has(x));
                const existingLines = [...existingQ].filter(x => lineLabels.has(x));

                let lineConflict = false;
                if (sourceLines.length && existingLines.length) {
                    lineConflict = !sourceLines.some(x => existingLines.includes(x));
                }

                const keySettingLabels = new Set([
                    "maintenance","post-transplant","transplant-ineligible","adjuvant",
                    "neoadjuvant","cspc","crpc","post-cd38","double-class-exposed",
                    "squamous","non-squamous"
                ]);

                const sourceKey = [...sourceQ].filter(x => keySettingLabels.has(x));
                const existingKey = [...existingQ].filter(x => keySettingLabels.has(x));

                const keyConflict =
                    sourceKey.length > 0 &&
                    existingKey.length > 0 &&
                    !sourceKey.some(x => existingKey.includes(x));

                return {
                    sourceQualifiers: [...sourceQ],
                    existingQualifiers: [...existingQ],
                    shared,
                    lineConflict,
                    keyConflict
                };
            }

            /* ------------------------------------------------------------
               Phase/state compatibility
               ------------------------------------------------------------ */

            function stageRank(v) {
                const s = norm(v);
                if (s.includes("approved")) return 5;
                if (s.includes("filed") || s.includes("registration") || s.includes("reg review")) return 4;
                if (s.includes("phase 3")) return 3;
                if (s.includes("phase 2")) return 2;
                if (s.includes("phase 1")) return 1;
                return 0;
            }
            function phaseEvidence(sourceRow, record, f) {
                const source = clean(sourceRow.phase);
                const existing = selectText(record, f.phase);
                const exact = norm(source) === norm(existing);
                const sr = stageRank(source);
                const er = stageRank(existing);

                return {
                    source,
                    existing,
                    exact,
                    existingAhead: er > sr && er >= 4,
                    sourceAhead: sr > er && er > 0
                };
            }

            /* ------------------------------------------------------------
               HTTP
               ------------------------------------------------------------ */

            async function sleep(ms) {
                await new Promise(resolve => setTimeout(resolve, ms));
            }

            async function getJson(path) {
                const retryableStatuses = new Set([408, 429, 500, 502, 503, 504]);
                const attempts = 2;
                let lastError = null;

                for (let attempt = 1; attempt <= attempts; attempt++) {
                    try {
                        const res = await fetch(`${ADAPTER_BASE_URL}${path}`, {
                            method: "GET",
                            headers: {
                                "Accept": "application/json",
                                "X-Adapter-Key": adapterApiKey,
                            },
                        });

                        const body = await res.text();
                        let data;
                        try { data = JSON.parse(body); }
                        catch (_) {
                            throw new Error(
                                `Adapter returned non-JSON. status=${res.status}; ` +
                                `body=${body.slice(0,500)}`
                            );
                        }

                        if (res.ok) return data;

                        const err = new Error(
                            `Adapter request failed. status=${res.status}; ` +
                            `detail=${JSON.stringify(data).slice(0,700)}`
                        );

                        if (!retryableStatuses.has(res.status) || attempt === attempts) {
                            throw err;
                        }

                        lastError = err;
                        await sleep(1500);
                    } catch (error) {
                        lastError = error;

                        // Network/runtime fetch errors also get one retry. The common case
                        // is Render free-tier cold start: the first request may wake the
                        // service even if Airtable receives a 408.
                        if (attempt === attempts) throw error;
                        await sleep(1500);
                    }
                }

                throw lastError || new Error("Adapter request failed after retry.");
            }

            /* ------------------------------------------------------------
               1) Resolve Source Watch -> Company -> validated adapter route
               ------------------------------------------------------------ */

            const sourceWatchCompanyField = sourceWatchTable.getField("Company");
            const sourceWatchNameField = sourceWatchTable.getField("Source Name");
            const sourceWatchStatusField = sourceWatchTable.getField("Monitoring Status");
            const sourceWatchAdapterStatusField = sourceWatchTable.getField("Pipeline Adapter Status");
            const sourceWatchSourceUrlField = sourceWatchTable.getField("Source URL");
            const sourceWatchMachineUrlField = sourceWatchTable.getField("Machine Source URL");
            const sourceWatchAdapterRegistryField = sourceWatchTable.getField("Adapter Registry");
            const sourceWatchBindingStatusField = sourceWatchTable.getField("Adapter Binding Status");
            const sourceWatchRetrievalModeField = sourceWatchTable.getField("Retrieval Mode");

            const sourceWatchRecord = await sourceWatchTable.selectRecordAsync(
                sourceWatchRecordId
            );

            if (!sourceWatchRecord) {
                throw new Error(
                    `Source Watch record not found: ${sourceWatchRecordId}`
                );
            }

            const monitoringStatus = norm(
                sourceWatchRecord.getCellValueAsString(sourceWatchStatusField)
            );

            if (monitoringStatus !== "active") {
                throw new Error(
                    `Source Watch record ${sourceWatchRecordId} has Monitoring Status ` +
                    `"${sourceWatchRecord.getCellValueAsString(sourceWatchStatusField)}". ` +
                    `Only Active sources are processed.`
                );
            }

            const pipelineAdapterStatus = norm(
                sourceWatchRecord.getCellValueAsString(sourceWatchAdapterStatusField)
            );

            if (pipelineAdapterStatus !== "validated") {
                throw new Error(
                    `Source Watch record ${sourceWatchRecordId} has Pipeline Adapter Status ` +
                    `"${sourceWatchRecord.getCellValueAsString(sourceWatchAdapterStatusField)}". ` +
                    `Only Validated pipeline sources are processed.`
                );
            }

            const companyLinks = sourceWatchRecord.getCellValue(sourceWatchCompanyField) || [];

            if (!Array.isArray(companyLinks) || companyLinks.length !== 1) {
                throw new Error(
                    `Source Watch ${sourceWatchRecordId} must link to exactly one Company; found ${companyLinks.length}.`
                );
            }

            const companyRecordId = companyLinks[0].id;

            const companyNameField = companiesTable.getField("Name");
            const targetCompany = await companiesTable.selectRecordAsync(companyRecordId);

            if (!targetCompany) {
                throw new Error(
                    `Company record linked from Source Watch was not found: ${companyRecordId}`
                );
            }

            const companyName = clean(
                targetCompany.getCellValueAsString(companyNameField)
            );

            const sourceWatchName = clean(
                sourceWatchRecord.getCellValueAsString(sourceWatchNameField)
            );

            if (!norm(sourceWatchName).includes("pipeline")) {
                throw new Error(
                    `Source Watch "${sourceWatchName}" is not a pipeline source. ` +
                    `This V2.58.0 monitor only processes validated pipeline sources.`
                );
            }

            const adapterLinks = sourceWatchRecord.getCellValue(sourceWatchAdapterRegistryField) || [];
            if (!Array.isArray(adapterLinks) || adapterLinks.length !== 1) {
                throw new Error(
                    `Source Watch ${sourceWatchRecordId} must link to exactly one Adapter Registry record; found ${adapterLinks.length}.`
                );
            }

            const adapterRecord = await adaptersTable.selectRecordAsync(adapterLinks[0].id);
            if (!adapterRecord) {
                throw new Error(
                    `Adapter Registry record not found: ${adapterLinks[0].id}`
                );
            }

            const adapterProfileField = adaptersTable.getField("Adapter Profile");
            const adapterStatusField = adaptersTable.getField("Adapter Status");
            const adapterHandlerField = adaptersTable.getField("Endpoint / Handler");
            const adapterRetrievalModesField = adaptersTable.getField("Supported Retrieval Modes");

            const adapterProfile = clean(adapterRecord.getCellValueAsString(adapterProfileField));
            const adapterStatus = norm(adapterRecord.getCellValueAsString(adapterStatusField));
            const adapterHandlerRaw = clean(adapterRecord.getCellValueAsString(adapterHandlerField));
            const adapterHandlerPath = adapterHandlerRaw.replace(/^pharma-pipeline-pdf-adapter:/i, "");

            if (adapterStatus !== "validated") {
                throw new Error(
                    `Adapter Registry profile "${adapterProfile}" is ` +
                    `"${adapterRecord.getCellValueAsString(adapterStatusField)}", not Validated.`
                );
            }

            if (!adapterHandlerPath || !adapterHandlerPath.startsWith("/")) {
                throw new Error(
                    `Adapter Registry profile "${adapterProfile}" has invalid Endpoint / Handler "${adapterHandlerRaw}".`
                );
            }

            const retrievalMode = clean(
                sourceWatchRecord.getCellValueAsString(sourceWatchRetrievalModeField)
            );
            const supportedRetrievalModes = (
                sourceWatchRecord && adapterRecord.getCellValue(adapterRetrievalModesField) || []
            ).map(x => clean(x && x.name)).filter(Boolean);

            if (!retrievalMode) {
                throw new Error(
                    `Source Watch "${sourceWatchName}" has no Retrieval Mode.`
                );
            }

            if (!supportedRetrievalModes.includes(retrievalMode)) {
                throw new Error(
                    `Source Watch retrieval mode "${retrievalMode}" is not supported by adapter "${adapterProfile}". ` +
                    `Supported modes: ${supportedRetrievalModes.join(", ") || "none"}.`
                );
            }

            const bindingStatus = norm(
                sourceWatchRecord.getCellValueAsString(sourceWatchBindingStatusField)
            );

            // Pfizer and Sanofi pre-date source-specific binding QA. Preserve their
            // already-validated specialised production routes while all newer routes require
            // a validated source+adapter binding.
            const legacyValidatedProfiles = new Set([
                "PIPELINE_PFIZER_PDF_V1",
                "PIPELINE_SANOFI_HTML_V1",
            ]);

            if (!legacyValidatedProfiles.has(adapterProfile) && bindingStatus !== "validated") {
                throw new Error(
                    `Source Watch "${sourceWatchName}" has Adapter Binding Status ` +
                    `"${sourceWatchRecord.getCellValueAsString(sourceWatchBindingStatusField)}". ` +
                    `A validated source+adapter binding is required for "${adapterProfile}".`
                );
            }

            const sourceUrl = clean(
                sourceWatchRecord.getCellValueAsString(sourceWatchMachineUrlField) ||
                sourceWatchRecord.getCellValueAsString(sourceWatchSourceUrlField)
            );

            if (!sourceUrl) {
                throw new Error(
                    `Source Watch "${sourceWatchName}" has no Source URL / Machine Source URL.`
                );
            }

            // Stable company key for queue deduplication. Pfizer/Sanofi remain unchanged.
            const companySlug = norm(companyName).replace(/\s+/g, "_");

            let adapterRequestPath = adapterHandlerPath;

            if (adapterHandlerPath === "/extract/generic/pipeline") {
                if (retrievalMode !== "DIRECT") {
                    throw new Error(
                        `PIPELINE_GENERIC_HTML_V1 requires DIRECT retrieval; source is "${retrievalMode}".`
                    );
                }
                adapterRequestPath =
                    `${adapterHandlerPath}?company=${encodeURIComponent(companyName)}&source_url=${encodeURIComponent(sourceUrl)}`;
            } else if (adapterHandlerPath === "/extract/generic/xlsx-pipeline") {
                if (retrievalMode !== "STATIC_DOCUMENT") {
                    throw new Error(
                        `PIPELINE_GENERIC_XLSX_V1 requires STATIC_DOCUMENT retrieval; source is "${retrievalMode}".`
                    );
                }
                adapterRequestPath =
                    `${adapterHandlerPath}?company=${encodeURIComponent(companyName)}&source_url=${encodeURIComponent(sourceUrl)}`;
            } else if (adapterHandlerPath === "/extract/generic/pdf-pipeline-table") {
                if (retrievalMode !== "STATIC_DOCUMENT") {
                    throw new Error(
                        `PIPELINE_GENERIC_PDF_TABLE_V1 requires STATIC_DOCUMENT retrieval; source is "${retrievalMode}".`
                    );
                }
                adapterRequestPath =
                    `${adapterHandlerPath}?company=${encodeURIComponent(companyName)}&source_url=${encodeURIComponent(sourceUrl)}`;
            } else if (adapterHandlerPath === "/extract/lilly/pipeline") {
                if (retrievalMode !== "STATIC_DOCUMENT") {
                    throw new Error(
                        `PIPELINE_LILLY_INVESTOR_PDF_V1 requires STATIC_DOCUMENT retrieval; source is "${retrievalMode}".`
                    );
                }
                // The source-specific Lilly endpoint owns its currently validated
                // first-party document URL and emits that URL in its response.
                adapterRequestPath = adapterHandlerPath;
            } else if (adapterHandlerPath === "/extract-bms-v4") {
                adapterRequestPath =
                    `${adapterHandlerPath}?source_url=${encodeURIComponent(sourceUrl)}`;
            } else if (
                adapterHandlerPath === "/extract/pfizer" ||
                adapterHandlerPath === "/extract/sanofi"
            ) {
                // Existing specialised endpoints require no source URL query parameter.
            } else {
                throw new Error(
                    `Validated adapter "${adapterProfile}" uses unsupported handler "${adapterHandlerPath}". ` +
                    `Failing closed until an explicit orchestration route is registered.`
                );
            }

            /* ------------------------------------------------------------
               2) Official source guardrail
               ------------------------------------------------------------ */

            const external = await getJson(adapterRequestPath);
            const allSourceRows = Array.isArray(external.rows) ? external.rows : [];
            // The pipeline monitor owns active development only. Approved /
            // commercial rows are handled by Products + Regulatory truth and
            // must not become "new development programme" queue candidates.
            const sourceRows = allSourceRows.filter(r => stageRank(r.phase) < 5);
            const outOfScopeApprovedRows = allSourceRows.length - sourceRows.length;

            const counts = {"Phase 1":0,"Phase 2":0,"Phase 3":0,"Filed / Registration":0};
            for (const r of sourceRows) if (counts[r.phase] !== undefined) counts[r.phase]++;

            const externalSummary = external.summary || {};
            const externalIssues = Array.isArray(external.issues) ? external.issues : [];
            const externalDiagnostics = external.diagnostics || {};

            const routeReady =
                [
                    "/extract/generic/pipeline",
                    "/extract/generic/xlsx-pipeline",
                    "/extract/generic/pdf-pipeline-table",
                    "/extract/lilly/pipeline"
                ].includes(adapterHandlerPath)
                    ? external.readyForDiscovery === true
                    : true;

            const guardrail =
                routeReady &&
                externalSummary.structuralValidationPass === true &&
                externalIssues.length === 0 &&
                Number(externalDiagnostics.rowFailures || 0) === 0 &&
                Number(externalDiagnostics.exactDuplicatesRemoved || 0) === 0 &&
                Number(externalDiagnostics.phaseUnresolved || 0) === 0 &&
                Number(externalDiagnostics.boundaryWarnings || 0) === 0 &&
                Number(externalDiagnostics.exactDuplicates || 0) === 0;

            if (!guardrail) {
                output.set("genericDeltaSummary", JSON.stringify({
                    version: VERSION,
                    company: companyName,
                    companyRecordId: targetCompany.id,
                    companySlug,
                    adapterProfile,
                    adapterHandlerPath,
                    retrievalMode,
                    sourceGuardrailPass: false,
                    officialRows: sourceRows.length,
                    outOfScopeApprovedRows,
                    counts,
                    adapterVersion: external.version || "",
                    adapterProductionStatus: externalSummary.productionStatus || "",
                    externalIssues,
                    status: "FAIL CLOSED - adapter/source structure requires review"
                }, null, 2));
                output.set("newProgrammes", "[]");
                output.set("phaseChanges", "[]");
                output.set("programmeChanges", "[]");
                output.set("sourceDisappearances", "[]");
                output.set("laterStagePreserved", "[]");
                output.set("matchReview", "[]");
                output.set("noChangeSample", "[]");
                return;
            }

            /* ------------------------------------------------------------
               3) Load Portfolio
               ------------------------------------------------------------ */

            const f = {
                company: field("Company"),
                brand: field("Brand / Asset"),
                molecule: field("Molecule / INN"),
                devCode: field("Development Code"),
                aliases: field("Asset Aliases / Former Codes"),
                indication: field("Indication"),
                phase: field("Development Phase"),
                status: field("Portfolio Status"),
                setting: field("Treatment Setting / Line"),
                segment: field("Biomarker / Patient Segment"),
                subtype: field("Disease Subtype"),
                clinicalTrials: field("Clinical Trials"),
                sourceUrl: field("Source URL")
            };

            for (const k of ["company","brand","molecule","indication","phase","status"]) {
                if (!f[k]) throw new Error(`Required Portfolio field missing: ${k}`);
            }

            const fields = unique(Object.values(f).filter(Boolean));
            const pq = await portfolioTable.selectRecordsAsync({fields});

            function isTargetCompany(record) {
                const raw = record.getCellValue(f.company);
                return Array.isArray(raw) && raw.some(x => x && x.id === targetCompany.id);
            }
            function isCurrentDevelopment(record) {
                const s = norm(selectText(record, f.status));
                const p = norm(selectText(record, f.phase));
                if (s === "marketed" || s === "discontinued") return false;
                if (s === "pipeline" || s.includes("filed")) return true;
                return /phase [123]|registration|filed/.test(p);
            }

            const existingAll = pq.records.filter(isTargetCompany);
            const existingDevelopment = existingAll.filter(isCurrentDevelopment);

            /* ------------------------------------------------------------
               4) Score source ↔ Portfolio pairs
               ------------------------------------------------------------ */

            // A source can contain a legitimate collision where asset + indication + phase are
            // identical for two source cards (SP0287), and the source description is the
            // only stable variant discriminator. Use that description ONLY for source
            // collision groups; do not make description a universal identity requirement.

            const sourceVariantCollisionKeys = new Set(
                (Array.isArray(externalDiagnostics.variantCollisions)
                    ? externalDiagnostics.variantCollisions
                    : []
                ).map(x => norm(x.key))
            );

            function sourceCoarseVariantKey(sourceRow) {
                return [
                    norm(sourceRow.asset),
                    norm(sourceRow.indication),
                    norm(sourceRow.phase)
                ].join(" ");
            }

            function sourceVariantQualifier(sourceRow) {
                const key = sourceCoarseVariantKey(sourceRow);

                const isCollision = [...sourceVariantCollisionKeys].some(k =>
                    compact(k) === compact(key)
                );

                return isCollision ? norm(sourceRow.description || "") : "";
            }

            function existingVariantQualifier(record) {
                const brand = clean(cellText(record, f.brand));
                const m = brand.match(/\(([^)]+)\)\s*$/);
                return m ? norm(m[1]) : "";
            }

            function variantEvidence(sourceRow, record) {
                const sourceVariant = sourceVariantQualifier(sourceRow);

                if (!sourceVariant) {
                    return {
                        required: false,
                        exact: false,
                        conflict: false,
                        sourceVariant: "",
                        existingVariant: ""
                    };
                }

                const existingVariant = existingVariantQualifier(record);
                const exact =
                    sourceVariant &&
                    existingVariant &&
                    (
                        compact(sourceVariant) === compact(existingVariant) ||
                        similarity(sourceVariant, existingVariant) >= 0.92
                    );

                return {
                    required: true,
                    exact,
                    conflict: !exact,
                    sourceVariant,
                    existingVariant
                };
            }

            function scorePair(sourceRow, record) {
                const id = identityEvidence(sourceRow, record, f);
                const whole = wholeIdentityEvidence(sourceRow, record, f);
                const prog = programmeMatchEvidence(sourceRow, record, f);
                const qual = qualifierEvidence(sourceRow, record, f);
                const phase = phaseEvidence(sourceRow, record, f);
                const variant = variantEvidence(sourceRow, record);
                const ind = indicationSimilarity(sourceRow.indication, cellText(record, f.indication));

                let score = 0;
                const reasons = [];

                if (prog.programmeMatch) {
                    score += 90;
                    reasons.push("linked Clinical Trial / study acronym match");
                }

                if (whole.exactWholeIdentity) {
                    score += 55;
                    reasons.push("whole asset/programme identity exact");
                }

                if (id.codeMatch) {
                    const codeWeight = Math.round(
                        35 + 25 * Math.max(
                            whole.sourceCodeCoverage,
                            whole.existingCodeCoverage
                        )
                    );
                    score += codeWeight;
                    reasons.push(`shared development code ${id.sharedCodes.join(", ")}`);
                }

                if (id.exactIdentity && !whole.exactWholeIdentity) {
                    score += 24;
                    reasons.push("partial asset/molecule identity");
                } else if (!id.exactIdentity) {
                    score += Math.round(id.identitySimilarity * 20);
                }

                if (phase.exact) {
                    score += 18;
                    reasons.push("phase exact");
                } else if (phase.existingAhead) {
                    score += 10;
                    reasons.push("existing regulatory state is ahead of R&D source; no downgrade");
                } else {
                    score -= 28;
                    reasons.push(`phase differs (${phase.existing || "blank"})`);
                }

                score += Math.round(ind * 34);
                if (ind >= 0.45) reasons.push(`indication similarity ${ind.toFixed(2)}`);

                score += Math.min(qual.shared.length * 8, 24);
                if (qual.shared.length) reasons.push(`shared qualifiers: ${qual.shared.join(", ")}`);

                if (variant.required) {
                    if (variant.exact) {
                        score += 60;
                        reasons.push(`source variant exact: ${variant.sourceVariant}`);
                    } else {
                        score -= 100;
                        reasons.push(
                            `source variant conflict: ${variant.sourceVariant} vs ` +
                            `${variant.existingVariant || "blank"}`
                        );
                    }
                }

                if (qual.lineConflict) {
                    score -= 38;
                    reasons.push("treatment-line conflict");
                }
                if (qual.keyConflict) {
                    score -= 28;
                    reasons.push("clinical-setting conflict");
                }

                return {
                    record,
                    score,
                    id,
                    whole,
                    prog,
                    qual,
                    phase,
                    variant,
                    indicationSimilarity: ind,
                    reasons
                };
            }

            const allPairs = [];
            for (let si = 0; si < sourceRows.length; si++) {
                const sourceRow = sourceRows[si];
                for (const record of existingDevelopment) {
                    const scored = scorePair(sourceRow, record);
                    allPairs.push({sourceIndex: si, sourceRow, ...scored});
                }
            }

            /* ------------------------------------------------------------
               5) Initial reconciliation programme grain
               ------------------------------------------------------------

               This is a read-only onboarding comparison. Existing rows are never split,
               overwritten, archived or deleted automatically. Distinct official source
               programmes remain distinct create candidates. Ambiguous identity is review-only.

               target company also has a known legitimate source variant collision (SP0287) where
               the same asset + indication + phase has two different vaccine combinations.
               The adapter preserves both source cards; this reconciliation must not dedupe them.
               ------------------------------------------------------------ */

            const splitExistingIds = new Set();
            const portfolioSplitRequired = [];

            /* ------------------------------------------------------------
               6) Build one-to-one assignments
               ------------------------------------------------------------ */

            const assignedSource = new Set();
            const assignedExisting = new Set();
            const confirmed = [];
            const stageConflictReview = [];

            const eligiblePairs = allPairs
                .filter(p => !splitExistingIds.has(p.record.id))
                .filter(p => {
                    if (!hasStrongIdentity(p)) return false;
                    if (p.qual.lineConflict || p.qual.keyConflict) return false;
                    if (p.variant.required && !p.variant.exact) return false;

                    // Recurring monitoring must still match the same programme when the
                    // source phase legitimately changes. Phase is therefore not allowed to
                    // break otherwise strong identity/programme-grain evidence.
                    const phaseTolerantIdentity =
                        p.prog.programmeMatch ||
                        p.whole.exactWholeIdentity ||
                        (
                            p.id.codeMatch &&
                            p.indicationSimilarity >= 0.45
                        ) ||
                        (
                            // A source may publish one recognised brand while Airtable
                            // stores a composite regional brand string. Permit a phase
                            // change to match when one identity component is exactly equal
                            // and the programme indication remains strongly aligned.
                            p.id.exactPartIdentity &&
                            p.whole.wholeIdentitySimilarity >= 0.80 &&
                            p.indicationSimilarity >= 0.60
                        );

                    return p.score >= 72 || phaseTolerantIdentity;
                })
                .sort((a,b) => {
                    // Direct programme/trial identity outranks generic similarity.
                    const ap = a.prog.programmeMatch ? 1 : 0;
                    const bp = b.prog.programmeMatch ? 1 : 0;
                    if (bp !== ap) return bp - ap;
                    return b.score - a.score;
                });

            for (const p of eligiblePairs) {
                if (assignedSource.has(p.sourceIndex)) continue;
                if (assignedExisting.has(p.record.id)) continue;

                const otherCandidatesForSource = eligiblePairs
                    .filter(x => x.sourceIndex === p.sourceIndex && x.record.id !== p.record.id)
                    .sort((a,b) => b.score - a.score);

                const second = otherCandidatesForSource[0] || null;
                const margin = p.score - (second ? second.score : 0);

                const directProgrammeResolution = p.prog.programmeMatch;
                const uniqueWholeIdentityResolution =
                    p.whole.exactWholeIdentity &&
                    p.indicationSimilarity >= 0.72 &&
                    !p.qual.lineConflict &&
                    !p.qual.keyConflict;

                const safeMargin =
                    directProgrammeResolution ||
                    uniqueWholeIdentityResolution ||
                    margin >= 10;

                if (!safeMargin) continue;

                // Do not auto-downgrade a later regulatory state.
                if (p.phase.existingAhead) {
                    assignedSource.add(p.sourceIndex);
                    assignedExisting.add(p.record.id);

                    stageConflictReview.push({
                        external: {
                            asset: p.sourceRow.asset,
                            indication: p.sourceRow.indication,
                            phase: p.sourceRow.phase,
                            sourcePage: p.sourceRow.sourcePage,
                            sourceRow: p.sourceRow.sourceRow,
                            sourceCardOrdinal: p.sourceRow.sourceCardOrdinal,
                            sourceDescription: p.sourceRow.description || ""
                        },
                        existing: {
                            recordId: p.record.id,
                            brandAsset: cellText(p.record, f.brand),
                            molecule: cellText(p.record, f.molecule),
                            indication: cellText(p.record, f.indication),
                            phase: selectText(p.record, f.phase),
                            portfolioStatus: selectText(p.record, f.status),
                            linkedTrials: linkNames(p.record, f.clinicalTrials)
                        },
                        decision:
                            "MATCH IDENTITY, PRESERVE LATER EXISTING STAGE. Do not downgrade Development Phase from the official R&D source.",
                        score: p.score,
                        reasons: p.reasons
                    });
                    continue;
                }

                assignedSource.add(p.sourceIndex);
                assignedExisting.add(p.record.id);

                confirmed.push({
                    external: {
                        asset: p.sourceRow.asset,
                        developmentCode: p.sourceRow.developmentCode,
                        indication: p.sourceRow.indication,
                        phase: p.sourceRow.phase,
                        mechanismOfAction: p.sourceRow.mechanismOfAction,
                        submissionType: p.sourceRow.submissionType,
                        sourcePage: p.sourceRow.sourcePage,
                        sourceRow: p.sourceRow.sourceRow,
                        sourceCardOrdinal: p.sourceRow.sourceCardOrdinal,
                        sourceDescription: p.sourceRow.description || "",
                        programmeTokens: p.prog.sourceTokens
                    },
                    existing: {
                        recordId: p.record.id,
                        brandAsset: cellText(p.record, f.brand),
                        molecule: cellText(p.record, f.molecule),
                        developmentCode: cellText(p.record, f.devCode),
                        indication: cellText(p.record, f.indication),
                        phase: selectText(p.record, f.phase),
                        portfolioStatus: selectText(p.record, f.status),
                        linkedTrials: linkNames(p.record, f.clinicalTrials)
                    },
                    score: p.score,
                    margin,
                    indicationSimilarity: Number(p.indicationSimilarity.toFixed(3)),
                    sourceQualifiers: p.qual.sourceQualifiers,
                    existingQualifiers: p.qual.existingQualifiers,
                    programmeMatch: p.prog.programmeMatch,
                    wholeIdentityExact: p.whole.exactWholeIdentity,
                    reasons: p.reasons
                });
            }

            /* ------------------------------------------------------------
               7) Classify remaining source rows
               ------------------------------------------------------------ */

            const distinctProgrammeCandidates = [];

            // Use all existing target-company Portfolio rows as identity context for classification,
            // including marketed/approved records. They are NEVER used for stale logic or
            // direct pipeline overwrites; they only tell us whether an official development
            // row belongs to an already-known asset family.
            const contextPairs = [];
            for (let si = 0; si < sourceRows.length; si++) {
                const sourceRow = sourceRows[si];
                for (const record of existingAll) {
                    const scored = scorePair(sourceRow, record);
                    contextPairs.push({sourceIndex: si, sourceRow, ...scored});
                }
            }

            function portfolioState(record) {
                return norm(selectText(record, f.status));
            }
            function isMarketedContext(record) {
                const s = portfolioState(record);
                const p = norm(selectText(record, f.phase));
                return s === "marketed" || p === "approved";
            }

            for (let i = 0; i < sourceRows.length; i++) {
                if (assignedSource.has(i)) continue;

                const row = sourceRows[i];

                const identityCandidates = contextPairs
                    .filter(p => p.sourceIndex === i && hasAnyIdentity(p))
                    .sort((a,b) => {
                        const ap = pIdentityPriority(a);
                        const bp = pIdentityPriority(b);
                        if (bp !== ap) return bp - ap;
                        return b.score - a.score;
                    });

                const genericCandidates = contextPairs
                    .filter(p => p.sourceIndex === i)
                    .sort((a,b) => b.score - a.score);

                const bestIdentity = identityCandidates[0] || null;
                const bestGeneric = genericCandidates[0] || null;

                let classification = "NEW OFFICIAL PROGRAMME";
                let reason = "No identity-bearing existing target-company Portfolio record matches this official programme.";

                if (
                    bestIdentity &&
                    splitExistingIds.has(bestIdentity.record.id) &&
                    hasStrongIdentity(bestIdentity)
                ) {
                    classification = "NEW PROGRAMME FROM EXISTING BROAD-ROW SPLIT";
                    reason = "This official programme belongs to an existing broad Portfolio row that has been proven to represent multiple distinct programmes.";
                } else if (bestIdentity && isMarketedContext(bestIdentity.record)) {
                    classification = "EXISTING MARKETED ASSET - NEW DEVELOPMENT PROGRAMME";
                    reason = "The asset already exists in marketed/approved Portfolio context, but this official row represents a distinct development indication/programme and should be created separately.";
                } else if (bestIdentity) {
                    classification = "SAME ASSET - DISTINCT DEVELOPMENT PROGRAMME";
                    reason = "Asset identity already exists, but this official row is not the same one-to-one programme. Preserve it as a separate development programme rather than overwriting the existing record.";
                }

                const diagnostic = bestIdentity || bestGeneric;

                distinctProgrammeCandidates.push({
                    classification,
                    reason,
                    external: {
                        asset: row.asset,
                        developmentCode: row.developmentCode,
                        indication: row.indication,
                        phase: row.phase,
                        mechanismOfAction: row.mechanismOfAction,
                        submissionType: row.submissionType,
                        sourcePage: row.sourcePage,
                        sourceRow: row.sourceRow,
                        sourceCardOrdinal: row.sourceCardOrdinal,
                        sourceDescription: row.description || "",
                        programmeTokens: programmeTokensFromSource(row.indication)
                    },
                    bestIdentityCandidate: bestIdentity ? {
                        recordId: bestIdentity.record.id,
                        brandAsset: cellText(bestIdentity.record, f.brand),
                        molecule: cellText(bestIdentity.record, f.molecule),
                        indication: cellText(bestIdentity.record, f.indication),
                        phase: selectText(bestIdentity.record, f.phase),
                        portfolioStatus: selectText(bestIdentity.record, f.status),
                        linkedTrials: linkNames(bestIdentity.record, f.clinicalTrials),
                        score: bestIdentity.score,
                        wholeIdentityExact: bestIdentity.whole.exactWholeIdentity,
                        wholeIdentitySimilarity: Number(bestIdentity.whole.wholeIdentitySimilarity.toFixed(3)),
                        reasons: bestIdentity.reasons
                    } : null,
                    genericBestForDiagnostics: diagnostic ? {
                        recordId: diagnostic.record.id,
                        brandAsset: cellText(diagnostic.record, f.brand),
                        score: diagnostic.score,
                        reasons: diagnostic.reasons
                    } : null
                });
            }

            function pIdentityPriority(p) {
                if (p.prog.programmeMatch) return 5;
                if (p.whole.exactWholeIdentity) return 4;
                if (p.id.codeMatch && p.whole.sourceCodeCoverage >= 0.5) return 3;
                if (p.id.codeMatch) return 2;
                if (p.id.exactIdentity) return 1;
                return 0;
            }

            /* ------------------------------------------------------------
               7b) Alias / renamed-code review candidates
               ------------------------------------------------------------ */

            const aliasReviewCandidates = [];

            for (const existing of existingDevelopment) {
                if (assignedExisting.has(existing.id)) continue;
                if (splitExistingIds.has(existing.id)) continue;

                const candidatesForExisting = allPairs
                    .filter(p => p.record.id === existing.id)
                    .filter(p => !assignedSource.has(p.sourceIndex))
                    .filter(p => !hasAnyIdentity(p))
                    .filter(p =>
                        p.indicationSimilarity >= 0.70 &&
                        (
                            p.phase.exact ||
                            p.phase.existingAhead ||
                            stageRank(p.phase.source) >= 3
                        )
                    )
                    .sort((a,b) => {
                        if (b.indicationSimilarity !== a.indicationSimilarity) {
                            return b.indicationSimilarity - a.indicationSimilarity;
                        }
                        return b.score - a.score;
                    })
                    .slice(0,5);

                if (!candidatesForExisting.length) continue;

                aliasReviewCandidates.push({
                    existing: {
                        recordId: existing.id,
                        brandAsset: cellText(existing, f.brand),
                        molecule: cellText(existing, f.molecule),
                        developmentCode: cellText(existing, f.devCode),
                        aliases: cellText(existing, f.aliases),
                        indication: cellText(existing, f.indication),
                        phase: selectText(existing, f.phase),
                        portfolioStatus: selectText(existing, f.status),
                        linkedTrials: linkNames(existing, f.clinicalTrials)
                    },
                    reviewReason:
                        "No direct identity token matched, but indication/stage evidence suggests a renamed asset or changed development code may exist. Verify with an authoritative company/regulatory source and add the verified former/current code to Asset Aliases / Former Codes before any write.",
                    possibleOfficialRows: candidatesForExisting.map(p => ({
                        asset: p.sourceRow.asset,
                        developmentCode: p.sourceRow.developmentCode,
                        indication: p.sourceRow.indication,
                        phase: p.sourceRow.phase,
                        indicationSimilarity: Number(p.indicationSimilarity.toFixed(3)),
                        sourcePage: p.sourceRow.sourcePage,
                        sourceRow: p.sourceRow.sourceRow
                    }))
                });
            }

            /* ------------------------------------------------------------
               8) Existing current-development rows not represented
               ------------------------------------------------------------ */

            const unmatchedExisting = existingDevelopment
                .filter(r => !assignedExisting.has(r.id) && !splitExistingIds.has(r.id))
                .map(r => ({
                    recordId: r.id,
                    brandAsset: cellText(r, f.brand),
                    molecule: cellText(r, f.molecule),
                    developmentCode: cellText(r, f.devCode),
                    indication: cellText(r, f.indication),
                    phase: selectText(r, f.phase),
                    portfolioStatus: selectText(r, f.status),
                    linkedTrials: linkNames(r, f.clinicalTrials),
                    sourceUrl: cellText(r, f.sourceUrl),
                    action: "REVIEW ONLY - never auto-delete/archive from one source refresh"
                }));

            /* ------------------------------------------------------------
               9) Generic recurring delta classification
               ------------------------------------------------------------ */

            function materiallyDifferentProgramme(match) {
                if (match.indicationSimilarity >= 0.55) return false;
                if (match.programmeMatch) return false;
                return true;
            }

            function sourceLocator(row) {
                const locator = {};
                if (row.sourcePage !== undefined && row.sourcePage !== null) {
                    locator.sourcePage = row.sourcePage;
                }
                if (row.sourceRow !== undefined && row.sourceRow !== null) {
                    locator.sourceRow = row.sourceRow;
                }
                if (row.sourceCardOrdinal !== undefined && row.sourceCardOrdinal !== null) {
                    locator.sourceCardOrdinal = row.sourceCardOrdinal;
                }
                if (row.sourceDescription) {
                    locator.sourceDescription = row.sourceDescription;
                }
                return locator;
            }

            const phaseChanges = [];
            const programmeChanges = [];
            const noChange = [];

            for (const match of confirmed) {
                const sourcePhase = norm(match.external.phase);
                const existingPhase = norm(match.existing.phase);

                if (sourcePhase !== existingPhase) {
                    phaseChanges.push({
                        classification: "PHASE CHANGE",
                        existingRecordId: match.existing.recordId,
                        asset: match.external.asset,
                        programmeIndication: match.external.indication,
                        previousPhase: match.existing.phase,
                        sourcePhase: match.external.phase,
                        ...sourceLocator(match.external),
                        sourceUrl: external.sourceUrl || "",
                        confidence: "High",
                        evidence: match.reasons
                    });
                    continue;
                }

                if (materiallyDifferentProgramme(match)) {
                    programmeChanges.push({
                        classification: "INDICATION / PROGRAMME CHANGE",
                        existingRecordId: match.existing.recordId,
                        asset: match.external.asset,
                        previousIndication: match.existing.indication,
                        sourceIndication: match.external.indication,
                        phase: match.external.phase,
                        indicationSimilarity: match.indicationSimilarity,
                        ...sourceLocator(match.external),
                        sourceUrl: external.sourceUrl || "",
                        confidence: "Review",
                        evidence: match.reasons
                    });
                    continue;
                }

                noChange.push({
                    classification: "NO CHANGE",
                    existingRecordId: match.existing.recordId,
                    asset: match.external.asset,
                    programmeIndication: match.external.indication,
                    phase: match.external.phase
                });
            }

            const laterStagePreserved = stageConflictReview.map(x => ({
                classification: "LATER STAGE PRESERVED",
                existingRecordId: x.existing.recordId,
                asset: x.external.asset,
                programmeIndication: x.external.indication,
                sourcePhase: x.external.phase,
                airtablePhase: x.existing.phase,
                decision: x.decision
            }));

            const newProgrammes = distinctProgrammeCandidates.map(x => ({
                classification: "NEW PROGRAMME",
                subtype: x.classification,
                asset: x.external.asset,
                developmentCode: x.external.developmentCode,
                programmeIndication: x.external.indication,
                phase: x.external.phase,
                mechanismOfAction: x.external.mechanismOfAction,
                ...sourceLocator(x.external),
                sourceUrl: external.sourceUrl || "",
                identityContext: x.bestIdentityCandidate || null,
                reason: x.reason
            }));

            const sourceDisappearances = unmatchedExisting.map(x => ({
                classification: "SOURCE DISAPPEARANCE",
                ...x,
                decision:
                    "Review only. Absence from one official pipeline snapshot is not proof of discontinuation."
            }));

            const matchReview = [
                ...portfolioSplitRequired.map(x => ({
                    reviewType: "PROGRAMME GRAIN / SPLIT REVIEW",
                    ...x
                })),
                ...aliasReviewCandidates.map(x => ({
                    reviewType: "ASSET ALIAS / RENAME REVIEW",
                    ...x
                }))
            ];

            const materialDeltaCount =
                newProgrammes.length +
                phaseChanges.length +
                programmeChanges.length +
                sourceDisappearances.length;

            const matchedCoverage =
                confirmed.length +
                stageConflictReview.length;

            const queueWriteReady =
                guardrail &&
                matchReview.length === 0 &&
                matchedCoverage + newProgrammes.length === sourceRows.length &&
                matchedCoverage + sourceDisappearances.length === existingDevelopment.length;

            const sourceVariantCollisions =
                Array.isArray(externalDiagnostics.variantCollisions)
                    ? externalDiagnostics.variantCollisions
                    : [];

            const cleanSnapshot =
                queueWriteReady &&
                materialDeltaCount === 0;

            output.set("genericDeltaSummary", JSON.stringify({
                version: VERSION,
                company: companyName,
                companyRecordId: targetCompany.id,
                companySlug,
                adapterProfile,
                adapterHandlerPath,
                retrievalMode,

                sourceGuardrailPass: guardrail,
                adapterVersion: external.version || "",
                adapterProductionStatus: externalSummary.productionStatus || "",
                sourceDate: external.sourceDate || "",
                sourceUrl: external.sourceUrl || "",

                officialRows: sourceRows.length,
                outOfScopeApprovedRows,
                sourceCounts: counts,
                historicalBaselineCoverageMatches:
                    externalSummary.baselineCoverageMatches === true,

                existingCompanyPortfolioRows: existingAll.length,
                existingCurrentDevelopmentRows: existingDevelopment.length,

                matchedProgrammeRows: confirmed.length,
                laterStagePreserved: laterStagePreserved.length,
                noChange: noChange.length,
                phaseChanges: phaseChanges.length,
                programmeChanges: programmeChanges.length,
                newProgrammes: newProgrammes.length,
                sourceDisappearances: sourceDisappearances.length,
                matchReviewRequired: matchReview.length,
                sourceVariantCollisionCount: sourceVariantCollisions.length,
                materialDeltaCount,

                queueWriteReady,
                cleanSnapshot,
                writesApplied: false,

                status:
                    !queueWriteReady
                        ? "HOLD - identity/coverage review required"
                        : materialDeltaCount > 0
                            ? "DELTA DETECTED - ready for generic queue router"
                            : `CLEAN SNAPSHOT - no material ${companyName} pipeline delta detected`,

                safeguards: [
                    "The reconciliation layer makes no Portfolio master-data writes; only controlled queue routing and Source Watch metadata refresh are allowed.",
                    "Historical source counts are informational only; structural adapter validation is the production guardrail.",
                    "Phase differences do not break otherwise strong programme identity.",
                    "A later verified regulatory stage in Airtable is preserved and is not treated as a downgrade.",
                    "Source disappearance is review-only and never causes automatic deletion, archive or discontinuation.",
                    "Source-level variant collisions are preserved using source description only when the adapter explicitly identifies a collision.",
                    "Only sources with validated Source Watch eligibility and a validated Adapter Registry route are allowed; unsupported routes fail closed."
                ]
            }, null, 2));

            output.set("newProgrammes", JSON.stringify(newProgrammes, null, 2));
            output.set("phaseChanges", JSON.stringify(phaseChanges, null, 2));
            output.set("programmeChanges", JSON.stringify(programmeChanges, null, 2));
            output.set("sourceDisappearances", JSON.stringify(sourceDisappearances, null, 2));
            output.set("laterStagePreserved", JSON.stringify(laterStagePreserved, null, 2));
            output.set("matchReview", JSON.stringify(matchReview, null, 2));
            output.set("noChangeSample", JSON.stringify(noChange.slice(0, 20), null, 2));
            output.set("sourceVariantCollisions", JSON.stringify(sourceVariantCollisions, null, 2));


            /* ------------------------------------------------------------
               10) Generic Intelligence Update Queue router + Source Watch
               ------------------------------------------------------------

               Production principle
               --------------------
               - Detect pipeline deltas automatically.
               - Never directly modify Portfolio master intelligence.
               - Route material deltas into Intelligence Update Queue.
               - Refresh Source Watch only after a structurally valid, reconciliation-ready run.
               - Deduplicate repeat detections by stable Update ID.
               ------------------------------------------------------------ */

            const ROUTER_VERSION =
                "V2.59.0 SOURCE-WATCH-DRIVEN REGISTRY-ROUTED PIPELINE MONITOR + MULTI-STATIC DOCUMENT ROUTING + QUEUE ROUTER";

            function tableField(table, name) {
                try { return table.getField(name); } catch (_) { return null; }
            }

            function requireField(table, name) {
                const f = tableField(table, name);
                if (!f) throw new Error(`Required field missing: ${table.name}.${name}`);
                return f;
            }

            const qf = {
                updateId: requireField(updateQueueTable, "Update ID"),
                company: requireField(updateQueueTable, "Company"),
                portfolio: requireField(updateQueueTable, "Portfolio Record"),
                sourceWatch: requireField(updateQueueTable, "Source Watch"),
                targetTable: requireField(updateQueueTable, "Target Table"),
                targetRecord: requireField(updateQueueTable, "Target Record Key / ID"),
                actionType: requireField(updateQueueTable, "Action Type"),
                fieldAffected: requireField(updateQueueTable, "Field Affected"),
                currentValue: requireField(updateQueueTable, "Current Value"),
                proposedValue: requireField(updateQueueTable, "Proposed Value"),
                whatChanged: requireField(updateQueueTable, "What Changed"),
                sourceUrl: requireField(updateQueueTable, "Source URL"),
                sourcePublicationDate: requireField(updateQueueTable, "Source Publication Date"),
                detectedDate: requireField(updateQueueTable, "Detected Date"),
                confidence: requireField(updateQueueTable, "Confidence"),
                materiality: requireField(updateQueueTable, "Materiality"),
                reviewStatus: requireField(updateQueueTable, "Review Status"),
                createSignal: requireField(updateQueueTable, "Create Signal?"),
                targetModule: requireField(updateQueueTable, "Target Module (Controlled)"),
                targetModuleV2: requireField(updateQueueTable, "Target Module v2 (Controlled)"),
                resolverVersion: requireField(updateQueueTable, "Resolver Version"),
                resolverLastRun: requireField(updateQueueTable, "Resolver Last Run"),
                resolverNotes: requireField(updateQueueTable, "Resolver Notes")
            };

            const swf = {
                company: requireField(sourceWatchTable, "Company"),
                sourceName: requireField(sourceWatchTable, "Source Name"),
                lastChecked: requireField(sourceWatchTable, "Last Checked"),
                nextCheck: requireField(sourceWatchTable, "Next Check"),
                lastChange: requireField(sourceWatchTable, "Last Change Detected"),
                stateNotes: requireField(sourceWatchTable, "Last Known State / Notes"),
                confidence: requireField(sourceWatchTable, "Confidence")
            };

            function selectChoiceNames(fieldObj) {
                return (
                    fieldObj &&
                    fieldObj.options &&
                    Array.isArray(fieldObj.options.choices)
                ) ? fieldObj.options.choices.map(x => x.name) : [];
            }

            function assertSelectValue(fieldObj, value, label) {
                const choices = selectChoiceNames(fieldObj);
                if (!choices.includes(value)) {
                    throw new Error(
                        `${label} value "${value}" is not configured in Airtable. ` +
                        `Available: ${choices.join(", ")}`
                    );
                }
            }

            // Fail closed before any write if schema/select choices drift.
            for (const [fieldObj, value, label] of [
                [qf.targetTable, "Portfolio", "Target Table"],
                [qf.targetModule, "Portfolio", "Target Module (Controlled)"],
                [qf.targetModuleV2, "Portfolio", "Target Module v2 (Controlled)"],
                [qf.reviewStatus, "New", "Review Status"],
                [qf.confidence, "High", "Confidence"],
                [qf.materiality, "High", "Materiality"],
                [qf.materiality, "Medium", "Materiality"],
                [qf.actionType, "Update Existing", "Action Type"],
                [qf.actionType, "Create New Record", "Action Type"],
                [qf.actionType, "Needs Investigation", "Action Type"],
                [swf.confidence, "High", "Source Watch Confidence"]
            ]) {
                assertSelectValue(fieldObj, value, label);
            }

            function safeKey(value) {
                return norm(value)
                    .replace(/\s+/g, "_")
                    .slice(0, 120);
            }

            function parseSourceDateToISO(value) {
                const s = clean(value);
                if (!s) return "";
                const d = new Date(s);
                if (Number.isNaN(d.getTime())) return "";
                return d.toISOString().slice(0, 10);
            }

            function isoDatePlusDays(dateStr, days) {
                const d = new Date(`${dateStr}T12:00:00Z`);
                d.setUTCDate(d.getUTCDate() + days);
                return d.toISOString().slice(0, 10);
            }

            function queueMateriality(delta) {
                const sourcePhase = norm(
                    delta.sourcePhase ||
                    delta.phase ||
                    delta.airtablePhase ||
                    ""
                );

                if (delta.classification === "PHASE CHANGE") {
                    if (
                        sourcePhase.includes("phase 3") ||
                        sourcePhase.includes("filed") ||
                        sourcePhase.includes("registration")
                    ) return "High";
                    return "Medium";
                }

                if (delta.classification === "SOURCE DISAPPEARANCE") {
                    const existingPhase = norm(delta.phase || "");
                    if (
                        existingPhase.includes("phase 3") ||
                        existingPhase.includes("filed") ||
                        existingPhase.includes("registration")
                    ) return "High";
                    return "Medium";
                }

                if (delta.classification === "NEW PROGRAMME") {
                    if (
                        sourcePhase.includes("phase 3") ||
                        sourcePhase.includes("filed") ||
                        sourcePhase.includes("registration")
                    ) return "High";
                    return "Medium";
                }

                return "Medium";
            }

            function shouldCreateSignal(delta, materiality) {
                if (materiality === "High") return true;
                return delta.classification === "PHASE CHANGE";
            }

            function deltaUpdateId(delta) {
                const prefix = `${companySlug.toUpperCase()}_PIPELINE`;

                if (delta.classification === "PHASE CHANGE") {
                    return [
                        prefix,
                        "PHASE_CHANGE",
                        delta.existingRecordId,
                        safeKey(delta.previousPhase),
                        "TO",
                        safeKey(delta.sourcePhase)
                    ].join("|");
                }

                if (delta.classification === "INDICATION / PROGRAMME CHANGE") {
                    return [
                        prefix,
                        "PROGRAMME_CHANGE",
                        delta.existingRecordId,
                        safeKey(delta.sourceIndication)
                    ].join("|");
                }

                if (delta.classification === "SOURCE DISAPPEARANCE") {
                    return [
                        prefix,
                        "SOURCE_DISAPPEARANCE",
                        delta.recordId
                    ].join("|");
                }

                return [
                    prefix,
                    "NEW_PROGRAMME",
                    safeKey(delta.developmentCode || delta.asset),
                    safeKey(delta.programmeIndication),
                    safeKey(delta.phase),
                    safeKey(delta.sourceDescription || "")
                ].filter(Boolean).join("|");
            }

            function queueNarrative(delta) {
                if (delta.classification === "PHASE CHANGE") {
                    return {
                        action: "Update Existing",
                        field: "Development Phase",
                        current: delta.previousPhase || "",
                        proposed: delta.sourcePhase || "",
                        what:
                            `${delta.asset}: ${companyName} official pipeline moved this programme ` +
                            `from ${delta.previousPhase} to ${delta.sourcePhase}. ` +
                            `Identity matched to Portfolio ${delta.existingRecordId}.`
                    };
                }

                if (delta.classification === "INDICATION / PROGRAMME CHANGE") {
                    return {
                        action: "Needs Investigation",
                        field: "Indication / programme grain",
                        current: delta.previousIndication || "",
                        proposed: delta.sourceIndication || "",
                        what:
                            `${delta.asset}: official ${companyName} source wording materially differs ` +
                            `from the current Portfolio programme. Review whether this is a true ` +
                            `programme-grain change, population/label change, or source wording change.`
                    };
                }

                if (delta.classification === "SOURCE DISAPPEARANCE") {
                    return {
                        action: "Needs Investigation",
                        field: "Official pipeline source presence",
                        current:
                            `${delta.brandAsset || delta.molecule || "Programme"} | ` +
                            `${delta.indication || ""} | ${delta.phase || ""}`,
                        proposed: `Not present in current ${companyName} official pipeline snapshot`,
                        what:
                            `An existing ${companyName} development programme is absent from the latest ` +
                            `official pipeline snapshot. This is not treated as discontinuation. ` +
                            `Verify against company news, ClinicalTrials.gov and regulatory sources ` +
                            `before any master-data change.`
                    };
                }

                return {
                    action: "Create New Record",
                    field: "New Portfolio programme",
                    current: "No matched current-development Portfolio programme",
                    proposed:
                        `${delta.asset} | ${delta.programmeIndication} | ${delta.phase}`,
                    what:
                        `${companyName} official pipeline contains a programme that does not match an ` +
                        `existing current-development Portfolio row. Create only after controlled ` +
                        `indication/TA taxonomy resolution and duplicate review.`
                };
            }

            // Source Watch is supplied directly by the automation repeating group.
            // This avoids ambiguity when a company later has multiple monitored sources.

            const queueQuery = await updateQueueTable.selectRecordsAsync({
                fields: [qf.updateId, qf.reviewStatus]
            });

            const existingUpdateIds = new Set(
                queueQuery.records
                    .map(r => clean(r.getCellValueAsString(qf.updateId)))
                    .filter(Boolean)
            );

            const allMaterialDeltas = [
                ...newProgrammes,
                ...phaseChanges,
                ...programmeChanges,
                ...sourceDisappearances
            ];

            if (!queueWriteReady) {
                output.set("genericQueueRouterSummary", JSON.stringify({
                    version: ROUTER_VERSION,
                    company: companyName,
                    companyRecordId: targetCompany.id,
                    queueWriteReady: false,
                    writesApplied: false,
                    materialDeltasDetected: allMaterialDeltas.length,
                    queueItemsCreated: 0,
                    status: "ABORTED - generic delta engine is not queue-write ready"
                }, null, 2));

                throw new Error(
                    "V2.59.0 queue router aborted because generic delta engine is not queue-write ready."
                );
            }

            const detectedDate = new Date().toISOString().slice(0, 10);
            const sourcePublicationDate = parseSourceDateToISO(external.sourceDate);
            const resolverLastRun = new Date().toISOString();

            const queuePayloads = [];
            const dedupedExisting = [];

            for (const delta of allMaterialDeltas) {
                const updateId = deltaUpdateId(delta);

                if (existingUpdateIds.has(updateId)) {
                    dedupedExisting.push(updateId);
                    continue;
                }

                const narrative = queueNarrative(delta);
                const materiality = queueMateriality(delta);

                const fields = {};
                fields[qf.updateId.id] = updateId;
                fields[qf.company.id] = [{id: targetCompany.id}];

                const existingRecordId =
                    delta.existingRecordId ||
                    delta.recordId ||
                    "";

                if (existingRecordId) {
                    fields[qf.portfolio.id] = [{id: existingRecordId}];
                }

                fields[qf.sourceWatch.id] = [{id: sourceWatchRecord.id}];
                fields[qf.targetTable.id] = {name: "Portfolio"};
                fields[qf.targetModule.id] = {name: "Portfolio"};
                fields[qf.targetModuleV2.id] = {name: "Portfolio"};

                fields[qf.targetRecord.id] =
                    existingRecordId ||
                    `${delta.asset || ""}|${delta.programmeIndication || ""}`;

                fields[qf.actionType.id] = {name: narrative.action};
                fields[qf.fieldAffected.id] = narrative.field;
                fields[qf.currentValue.id] = narrative.current;
                fields[qf.proposedValue.id] = narrative.proposed;
                fields[qf.whatChanged.id] = narrative.what;

                fields[qf.sourceUrl.id] =
                    delta.sourceUrl ||
                    external.sourceUrl ||
                    "";

                if (sourcePublicationDate) {
                    fields[qf.sourcePublicationDate.id] = sourcePublicationDate;
                }

                fields[qf.detectedDate.id] = detectedDate;
                fields[qf.confidence.id] = {name: "High"};
                fields[qf.materiality.id] = {name: materiality};
                fields[qf.reviewStatus.id] = {name: "New"};
                fields[qf.createSignal.id] =
                    shouldCreateSignal(delta, materiality);

                fields[qf.resolverVersion.id] = ROUTER_VERSION;
                fields[qf.resolverLastRun.id] = resolverLastRun;
                fields[qf.resolverNotes.id] =
                    `Machine-detected from structurally validated ${companyName} official pipeline. ` +
                    `No Portfolio master-data change has been applied. ` +
                    `Review and approve through Intelligence Update Queue.`;

                queuePayloads.push({fields});
                existingUpdateIds.add(updateId);
            }

            const createdQueueIds = [];

            for (let i = 0; i < queuePayloads.length; i += 50) {
                const ids = await updateQueueTable.createRecordsAsync(
                    queuePayloads.slice(i, i + 50)
                );

                if (Array.isArray(ids)) {
                    createdQueueIds.push(...ids);
                }
            }

            // Current production pipeline Source Watch records are configured weekly.
            // Cadence remains Source Watch operational metadata; the delta engine stays
            // independent from company-specific routing.
            const nextCheck = isoDatePlusDays(detectedDate, 7);

            const sourceWatchFields = {
                [swf.lastChecked.id]: detectedDate,
                [swf.nextCheck.id]: nextCheck,
                [swf.confidence.id]: {name: "High"},
                [swf.stateNotes.id]:
                    `${ROUTER_VERSION}: ${sourceRows.length} active-development ${companyName} programmes parsed via ${adapterProfile}; ` +
                    `${outOfScopeApprovedRows} approved/commercial source row(s) kept out of pipeline-delta routing; ` +
                    `${noChange.length} unchanged, ${laterStagePreserved.length} later-stage preserved, ` +
                    `${phaseChanges.length} phase changes, ${programmeChanges.length} programme changes, ` +
                    `${newProgrammes.length} new programmes, ${sourceDisappearances.length} source disappearances. ` +
                    `${createdQueueIds.length} new queue item(s) created; ` +
                    `${dedupedExisting.length} already queued delta(s) suppressed.`
            };

            if (allMaterialDeltas.length > 0) {
                sourceWatchFields[swf.lastChange.id] = detectedDate;
            }

            await sourceWatchTable.updateRecordAsync(
                sourceWatchRecord.id,
                sourceWatchFields
            );

            output.set("genericQueueRouterSummary", JSON.stringify({
                version: ROUTER_VERSION,
                company: companyName,
                companyRecordId: targetCompany.id,
                companySlug,
                adapterProfile,
                adapterHandlerPath,
                retrievalMode,
                sourceWatchRecordId: sourceWatchRecord.id,
                sourceWatchName,

                queueWriteReady: true,
                writesApplied: true,

                sourceWatchRecordId: sourceWatchRecord.id,
                sourceWatchLastChecked: detectedDate,
                sourceWatchNextCheck: nextCheck,

                materialDeltasDetected: allMaterialDeltas.length,
                newProgrammesDetected: newProgrammes.length,
                phaseChangesDetected: phaseChanges.length,
                programmeChangesDetected: programmeChanges.length,
                sourceDisappearancesDetected: sourceDisappearances.length,

                queueItemsCreated: createdQueueIds.length,
                duplicateQueueItemsSuppressed: dedupedExisting.length,
                createdQueueRecordIds: createdQueueIds,

                status:
                    allMaterialDeltas.length === 0
                        ? `CLEAN RUN - ${companyName} Source Watch refreshed; no queue items required`
                        : createdQueueIds.length > 0
                            ? "MATERIAL DELTAS ROUTED TO INTELLIGENCE UPDATE QUEUE"
                            : "MATERIAL DELTAS ALREADY QUEUED - no duplicate queue records created",

                masterDataWrites: 0,

                principle:
                    "Pipeline deltas are detected automatically; Portfolio master changes remain controlled through Intelligence Update Queue review."
            }, null, 2));

            

      