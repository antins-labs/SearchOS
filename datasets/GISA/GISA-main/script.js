const data = [
  {
    model: "Qwen3-235B-A22B (thinking)",
    org: "Alibaba Cloud",
    framework: "ReAct",
    date: "2025.7",
    overall: 9.65,
    item_em: 40.91,
    set_em: 18.00,
    set_f1: 52.37,
    list_em: 14.58,
    list_f1: 36.48,
    list_order: 35.96,
    table_em: 4.35,
    table_row_f1: 28.32,
    table_item_f1: 43.93,
  },
  {
    model: "Claude 4.5 Sonnet (non-thinking)",
    org: "Anthropic AI",
    framework: "ReAct",
    date: "2025.9",
    overall: 16.36,
    item_em: 59.09,
    set_em: 26.00,
    set_f1: 60.87,
    list_em: 22.92,
    list_f1: 58.76,
    list_order: 57.78,
    table_em: 9.49,
    table_row_f1: 47.85,
    table_item_f1: 63.71,
  },
  {
    model: "Claude 4.5 Sonnet (thinking)",
    org: "Anthropic AI",
    framework: "ReAct",
    date: "2025.9",
    overall: 19.30,
    item_em: 63.64,
    set_em: 28.00,
    set_f1: 64.86,
    list_em: 22.92,
    list_f1: 59.24,
    list_order: 56.42,
    table_em: 13.04,
    table_row_f1: 49.92,
    table_item_f1: 65.17,
  },
  {
    model: "Gemini 3 Pro (low)",
    org: "Google",
    framework: "ReAct",
    date: "2025.11",
    overall: 14.74,
    item_em: 45.45,
    set_em: 28.00,
    set_f1: 63.82,
    list_em: 27.08,
    list_f1: 57.55,
    list_order: 56.37,
    table_em: 7.11,
    table_row_f1: 45.93,
    table_item_f1: 64.93,
  },
  {
    model: "Gemini 3 Pro (high)",
    org: "Google",
    framework: "ReAct",
    date: "2025.11",
    overall: 15.28,
    item_em: 50.00,
    set_em: 22.00,
    set_f1: 62.66,
    list_em: 27.08,
    list_f1: 60.87,
    list_order: 60.12,
    table_em: 8.70,
    table_row_f1: 47.01,
    table_item_f1: 66.02,
  },
  {
    model: "GPT-5.2 (thinking)",
    org: "OpenAI",
    framework: "ReAct",
    date: "2025.11",
    overall: 15.82,
    item_em: 63.64,
    set_em: 26.00,
    set_f1: 62.70,
    list_em: 16.67,
    list_f1: 54.11,
    list_order: 53.17,
    table_em: 9.49,
    table_row_f1: 43.04,
    table_item_f1: 60.20,
  },
  {
    model: "DeepSeek-V3.2 (non-thinking)",
    org: "DeepSeek AI",
    framework: "ReAct",
    date: "2025.12",
    overall: 11.53,
    item_em: 22.73,
    set_em: 20.00,
    set_f1: 52.00,
    list_em: 22.92,
    list_f1: 56.02,
    list_order: 55.45,
    table_em: 6.72,
    table_row_f1: 44.14,
    table_item_f1: 62.24,
  },
  {
    model: "DeepSeek-V3.2 (thinking)",
    org: "DeepSeek AI",
    framework: "ReAct",
    date: "2025.12",
    overall: 14.47,
    item_em: 63.64,
    set_em: 28.00,
    set_f1: 60.79,
    list_em: 20.83,
    list_f1: 62.25,
    list_order: 60.41,
    table_em: 6.32,
    table_row_f1: 43.44,
    table_item_f1: 62.42,
  },
  {
    model: "GLM-4.7 (thinking)",
    org: "Z.AI",
    framework: "ReAct",
    date: "2025.12",
    overall: 14.21,
    item_em: 50.00,
    set_em: 22.00,
    set_f1: 59.44,
    list_em: 20.83,
    list_f1: 51.99,
    list_order: 50.97,
    table_em: 8.30,
    table_row_f1: 43.97,
    table_item_f1: 61.28,
  },
  {
    model: "Seed-1.8 (thinking)",
    org: "ByteDance Seed",
    framework: "ReAct",
    date: "2025.12",
    overall: 13.40,
    item_em: 45.45,
    set_em: 32.00,
    set_f1: 56.77,
    list_em: 16.67,
    list_f1: 56.11,
    list_order: 53.54,
    table_em: 6.32,
    table_row_f1: 38.49,
    table_item_f1: 57.13,
  },
  {
    model: "Qwen3-Max (thinking)",
    org: "Alibaba Cloud",
    framework: "ReAct",
    date: "2026.1",
    overall: 17.96,
    item_em: 59.09,
    set_em: 30.00,
    set_f1: 63.45,
    list_em: 25.00,
    list_f1: 66.51,
    list_order: 64.08,
    table_em: 10.67,
    table_row_f1: 48.48,
    table_item_f1: 66.86,
  },
  {
    model: "Kimi K2.5 (thinking)",
    org: "Moonshot AI",
    framework: "ReAct",
    date: "2026.1",
    overall: 15.55,
    item_em: 68.18,
    set_em: 28.00,
    set_f1: 61.71,
    list_em: 18.75,
    list_f1: 50.52,
    list_order: 48.81,
    table_em: 7.91,
    table_row_f1: 45.19,
    table_item_f1: 61.23,
  },
  {
    model: "GPT-4o Search Preview",
    org: "OpenAI",
    framework: "N/A",
    date: "2025.3",
    overall: 5.63,
    item_em: 13.64,
    set_em: 4.00,
    set_f1: 38.70,
    list_em: 8.33,
    list_f1: 36.65,
    list_order: 36.00,
    table_em: 4.74,
    table_row_f1: 29.59,
    table_item_f1: 45.61,
  },
  {
    model: "OpenAI o4 Mini Deep Research",
    org: "OpenAI",
    framework: "N/A",
    date: "2025.6",
    overall: 7.78,
    item_em: 18.18,
    set_em: 14.00,
    set_f1: 63.03,
    list_em: 18.75,
    list_f1: 53.72,
    list_order: 52.59,
    table_em: 3.56,
    table_row_f1: 36.78,
    table_item_f1: 56.47,
  },
  {
    model: "Perplexity Sonar Pro Search",
    org: "Perplexity AI",
    framework: "N/A",
    date: "-",
    overall: 7.51,
    item_em: 22.73,
    set_em: 20.00,
    set_f1: 47.04,
    list_em: 6.25,
    list_f1: 34.74,
    list_order: 33.16,
    table_em: 3.95,
    table_row_f1: 34.76,
    table_item_f1: 49.05,
  },
  {
    model: "Google Search AI Mode",
    org: "Google",
    framework: "N/A",
    date: "-",
    overall: 9.38,
    item_em: 31.82,
    set_em: 20.00,
    set_f1: 46.34,
    list_em: 8.33,
    list_f1: 40.64,
    list_order: 39.36,
    table_em: 5.53,
    table_row_f1: 31.15,
    table_item_f1: 50.79,
  },
];

const tableBody = document.getElementById("leaderboard-body");
const searchInput = document.getElementById("search");
const headers = document.querySelectorAll("th[data-key]");

let sortKey = "overall";
let sortDir = "desc";

function renderRows() {
  const query = searchInput.value.trim().toLowerCase();

  const filtered = data
    .filter((row) => {
      if (!query) return true;
      return (
        row.model.toLowerCase().includes(query) ||
        row.org.toLowerCase().includes(query)
      );
    })
    .sort((a, b) => {
      const aVal = a[sortKey];
      const bVal = b[sortKey];
      if (sortKey === "date") {
        const toKey = (val) => {
          if (!val || val === "-") return null;
          const parts = String(val).split(".");
          const year = Number(parts[0]);
          const month = Number(parts[1] ?? 0);
          if (Number.isNaN(year) || Number.isNaN(month)) return null;
          return year * 100 + month;
        };
        const aKey = toKey(aVal);
        const bKey = toKey(bVal);
        if (aKey === null && bKey === null) return 0;
        if (aKey === null) return 1;
        if (bKey === null) return -1;
        return sortDir === "asc" ? aKey - bKey : bKey - aKey;
      }
      if (typeof aVal === "number" && typeof bVal === "number") {
        return sortDir === "asc" ? aVal - bVal : bVal - aVal;
      }
      return sortDir === "asc"
        ? String(aVal).localeCompare(String(bVal))
        : String(bVal).localeCompare(String(aVal));
    })
    .map((row, index) => ({ ...row, rank: index + 1 }));

  tableBody.innerHTML = filtered
    .map(
      (row) => `
      <tr>
        <td>${row.rank}</td>
        <td class="model-cell">
          <div class="model-name">${row.model}</div>
          <div class="model-org">${row.org}</div>
        </td>
        <td>${row.framework}</td>
        <td>${row.date}</td>
        <td class="highlight-em">${row.overall.toFixed(2)}</td>
        <td>${row.item_em.toFixed(2)}</td>
        <td>${row.set_em.toFixed(2)}</td>
        <td>${row.set_f1.toFixed(2)}</td>
        <td>${row.list_em.toFixed(2)}</td>
        <td>${row.list_f1.toFixed(2)}</td>
        <td>${row.list_order.toFixed(2)}</td>
        <td>${row.table_em.toFixed(2)}</td>
        <td>${row.table_row_f1.toFixed(2)}</td>
        <td>${row.table_item_f1.toFixed(2)}</td>
      </tr>`
    )
    .join("");
}

headers.forEach((th) => {
  th.addEventListener("click", () => {
    const key = th.dataset.key;
    if (key === sortKey) {
      sortDir = sortDir === "asc" ? "desc" : "asc";
    } else {
      sortKey = key;
      sortDir = key === "date" ? "desc" : "desc";
    }

    headers.forEach((h) => h.classList.remove("is-sorted"));
    th.classList.add("is-sorted");
    renderRows();
  });
});

searchInput.addEventListener("input", renderRows);

renderRows();

const copyBtn = document.getElementById("copy-citation");
const citationText = document.getElementById("citation-text");

if (copyBtn && citationText) {
  copyBtn.addEventListener("click", async () => {
    const text = citationText.innerText.trim();
    try {
      await navigator.clipboard.writeText(text);
      const original = copyBtn.textContent;
      copyBtn.textContent = "Copied";
      copyBtn.disabled = true;
      setTimeout(() => {
        copyBtn.textContent = original;
        copyBtn.disabled = false;
      }, 1400);
    } catch (err) {
      copyBtn.textContent = "Copy failed";
      setTimeout(() => {
        copyBtn.textContent = "Copy";
      }, 1600);
    }
  });
}
