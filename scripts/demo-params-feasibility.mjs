#!/usr/bin/env node

const MODELS_DEV_URL = "https://models.dev/api.json";

function toNumber(value) {
    if (typeof value === "number" && Number.isFinite(value)) return value;
    if (typeof value === "string") {
        const parsed = Number(value.replace(/,/g, "").trim());
        return Number.isFinite(parsed) ? parsed : null;
    }
    return null;
}

function parseParamsToB(raw) {
    if (raw == null) return null;

    if (typeof raw === "number") {
        if (!Number.isFinite(raw)) return null;
        if (raw > 1000) return raw / 1e9;
        return raw;
    }

    const text = String(raw).trim().toLowerCase();
    if (!text) return null;

    const xB = text.match(/(\d+(?:\.\d+)?)\s*x\s*(\d+(?:\.\d+)?)\s*b\b/i);
    if (xB) {
        const a = Number(xB[1]);
        const b = Number(xB[2]);
        if (Number.isFinite(a) && Number.isFinite(b)) return a * b;
    }

    const bMatch = text.match(/(\d+(?:\.\d+)?)\s*b\b/i);
    if (bMatch) {
        const n = Number(bMatch[1]);
        return Number.isFinite(n) ? n : null;
    }

    const mMatch = text.match(/(\d+(?:\.\d+)?)\s*m\b/i);
    if (mMatch) {
        const n = Number(mMatch[1]);
        return Number.isFinite(n) ? n / 1000 : null;
    }

    const n = toNumber(text);
    if (n != null) {
        if (n > 1000) return n / 1e9;
        return n;
    }

    return null;
}

function inferParamsFromName(modelId, name) {
    const text = `${modelId || ""} ${name || ""}`.toLowerCase();

    const xB = text.match(/\b(\d+(?:\.\d+)?)\s*x\s*(\d+(?:\.\d+)?)\s*b\b/i);
    if (xB) {
        const a = Number(xB[1]);
        const b = Number(xB[2]);
        if (Number.isFinite(a) && Number.isFinite(b)) return a * b;
    }

    const b = text.match(/\b(\d+(?:\.\d+)?)\s*b\b/i);
    if (b) {
        const n = Number(b[1]);
        if (Number.isFinite(n)) return n;
    }

    const m = text.match(/\b(\d+(?:\.\d+)?)\s*m\b/i);
    if (m) {
        const n = Number(m[1]);
        if (Number.isFinite(n)) return n / 1000;
    }

    return null;
}

function collectParamCandidates(model) {
    const candidates = [];

    for (const key of [
        "parameters",
        "params",
        "param",
        "model_params",
        "model_parameters",
        "weights",
        "size",
        "parameter_count",
    ]) {
        if (Object.prototype.hasOwnProperty.call(model, key)) {
            candidates.push({ key, value: model[key] });
        }
    }

    if (model.raw && typeof model.raw === "object") {
        for (const key of ["parameters", "params", "weights", "size"]) {
            if (Object.prototype.hasOwnProperty.call(model.raw, key)) {
                candidates.push({ key: `raw.${key}`, value: model.raw[key] });
            }
        }
    }

    return candidates;
}

async function fetchModels() {
    const response = await fetch(MODELS_DEV_URL, {
        headers: {
            accept: "application/json",
        },
    });

    if (!response.ok) {
        throw new Error(`Failed to fetch ${MODELS_DEV_URL}: HTTP ${response.status}`);
    }

    const json = await response.json();
    if (!json || typeof json !== "object") {
        throw new Error("Unexpected schema from models.dev/api.json");
    }

    const providerMap =
        json.provider && typeof json.provider === "object"
            ? json.provider
            : json;

    const rows = [];
    for (const [providerId, provider] of Object.entries(providerMap)) {
        const models = provider && typeof provider === "object" ? provider.models : null;
        if (!models || typeof models !== "object") continue;

        for (const [modelId, model] of Object.entries(models)) {
            rows.push({
                providerId,
                modelId,
                name: model?.name ?? null,
                family: model?.family ?? null,
                model,
            });
        }
    }

    return rows;
}

function analyze(rows) {
    let explicitCount = 0;
    let inferredCount = 0;
    let unknownCount = 0;

    const samples = [];

    for (const row of rows) {
        const candidates = collectParamCandidates(row.model);
        let explicitParamsB = null;
        let explicitSource = null;

        for (const c of candidates) {
            const parsed = parseParamsToB(c.value);
            if (parsed != null) {
                explicitParamsB = parsed;
                explicitSource = c.key;
                break;
            }
        }

        const inferredParamsB = explicitParamsB == null
            ? inferParamsFromName(row.modelId, row.name)
            : null;

        if (explicitParamsB != null) explicitCount += 1;
        else if (inferredParamsB != null) inferredCount += 1;
        else unknownCount += 1;

        const key = `${row.providerId}/${row.modelId}`.toLowerCase();
        if (
            key.includes("minimax") ||
            key.includes("gpt-5-mini") ||
            key.includes("gpt5-mini")
        ) {
            samples.push({
                id: `${row.providerId}/${row.modelId}`,
                name: row.name,
                explicitSource,
                explicitParamsB,
                inferredParamsB,
            });
        }
    }

    return {
        total: rows.length,
        explicitCount,
        inferredCount,
        unknownCount,
        samples,
    };
}

function printReport(result) {
    const pct = (n) => ((n / result.total) * 100).toFixed(2);

    console.log("=== Parameters Feasibility Demo (models.dev/api.json) ===");
    console.log(`total models: ${result.total}`);
    console.log(`explicit params: ${result.explicitCount} (${pct(result.explicitCount)}%)`);
    console.log(`name-inferred params: ${result.inferredCount} (${pct(result.inferredCount)}%)`);
    console.log(`unknown params: ${result.unknownCount} (${pct(result.unknownCount)}%)`);

    console.log("\n=== Focus models (minimax / gpt-5-mini) ===");
    if (result.samples.length === 0) {
        console.log("no matched model ids found");
        return;
    }

    for (const item of result.samples.slice(0, 20)) {
        console.log(JSON.stringify(item));
    }

    if (result.samples.length > 20) {
        console.log(`... and ${result.samples.length - 20} more matches`);
    }
}

async function main() {
    const rows = await fetchModels();
    const result = analyze(rows);
    printReport(result);
}

main().catch((error) => {
    console.error("demo failed:", error?.message || error);
    process.exitCode = 1;
});
