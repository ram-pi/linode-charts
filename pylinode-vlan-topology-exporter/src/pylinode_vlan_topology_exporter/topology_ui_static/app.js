const refreshSeconds = Number(window.TOPOLOGY_REFRESH_SECONDS || 5);

const summaryCards = document.getElementById("summaryCards");
const statusPill = document.getElementById("statusPill");
const lastUpdate = document.getElementById("lastUpdate");
const vlanTableBody = document.getElementById("vlanTableBody");
const attachmentTableBody = document.getElementById("attachmentTableBody");
const vlanCountLabel = document.getElementById("vlanCountLabel");
const attachmentCountLabel = document.getElementById("attachmentCountLabel");
const vlanSearchInput = document.getElementById("vlanSearchInput");
const attachmentSearchInput = document.getElementById("attachmentSearchInput");
const themeToggle = document.getElementById("themeToggle");
const toggleLabel = document.getElementById("toggleLabel");
const vlanPageSize = document.getElementById("vlanPageSize");
const attachmentPageSize = document.getElementById("attachmentPageSize");
const vlanPagination = document.getElementById("vlanPagination");
const attachmentPagination = document.getElementById("attachmentPagination");
const vlanFilterToggle = document.getElementById("vlanFilterToggle");
const attachmentFilterToggle = document.getElementById("attachmentFilterToggle");
const vlanFilterRow = document.getElementById("vlanFilterRow");
const attachmentFilterRow = document.getElementById("attachmentFilterRow");

let latest = null;
let vlanPage = 1;
let attachmentPage = 1;

function applyTheme(theme) {
  const isDark = theme === "dark";
  document.body.classList.toggle("dark", isDark);
  if (toggleLabel) {
    toggleLabel.textContent = isDark ? "Light mode" : "Dark mode";
  }
  if (themeToggle) {
    themeToggle.setAttribute("aria-pressed", isDark ? "true" : "false");
  }
}

function initializeTheme() {
  const storedTheme = localStorage.getItem("topology-ui-theme");
  if (storedTheme === "dark" || storedTheme === "light") {
    applyTheme(storedTheme);
    return;
  }
  const prefersDark = window.matchMedia && window.matchMedia("(prefers-color-scheme: dark)").matches;
  applyTheme(prefersDark ? "dark" : "light");
}

function setStatus(ok, text) {
  statusPill.className = `status-pill ${ok ? "status-ok" : "status-error"}`;
  statusPill.textContent = text;
}

function renderCards(data) {
  const cards = [
    ["VLANs", data.summary.vlan_count],
    ["Attachments", data.summary.attachment_count],
    ["Unique Linodes", data.summary.unique_linode_count],
    ["Scrape Success", data.scrape.success],
    ["Scrape Duration", `${data.scrape.duration_seconds}s`],
    ["Rate Limit Hits", data.scrape.api_rate_limit_hits_total],
  ];

  summaryCards.innerHTML = cards
    .map(
      ([title, value]) => `
      <article class="card">
        <p class="card-title">${title}</p>
        <p class="card-value">${value}</p>
      </article>
    `
    )
    .join("");
}

function tableRow(cells) {
  return `<tr>${cells.map((cell) => `<td>${cell}</td>`).join("")}</tr>`;
}

function filtered(data, query) {
  if (!query) {
    return data;
  }
  const q = query.toLowerCase();
  return data.filter((row) => JSON.stringify(row).toLowerCase().includes(q));
}

function paginate(data, pageSize, page) {
  const safePageSize = Number(pageSize || 25);
  const totalPages = Math.max(1, Math.ceil(data.length / safePageSize));
  const safePage = Math.min(Math.max(1, page), totalPages);
  const start = (safePage - 1) * safePageSize;
  return {
    rows: data.slice(start, start + safePageSize),
    page: safePage,
    totalPages,
  };
}

function renderPagination(container, page, totalPages, onPrev, onNext) {
  container.innerHTML = `
    <button type="button" ${page <= 1 ? "disabled" : ""} data-action="prev">Prev</button>
    <span>Page ${page} / ${totalPages}</span>
    <button type="button" ${page >= totalPages ? "disabled" : ""} data-action="next">Next</button>
  `;
  container.querySelector('[data-action="prev"]')?.addEventListener("click", onPrev);
  container.querySelector('[data-action="next"]')?.addEventListener("click", onNext);
}

function renderTables(data) {
  const vlanQuery = (vlanSearchInput.value || "").trim();
  const attachmentQuery = (attachmentSearchInput.value || "").trim();
  const vlanRows = filtered(data.vlans, vlanQuery);
  const attachmentRows = filtered(data.attachments, attachmentQuery);

  const vlanPaged = paginate(vlanRows, vlanPageSize.value, vlanPage);
  const attachmentPaged = paginate(attachmentRows, attachmentPageSize.value, attachmentPage);
  vlanPage = vlanPaged.page;
  attachmentPage = attachmentPaged.page;

  vlanCountLabel.textContent = String(vlanRows.length);
  attachmentCountLabel.textContent = String(attachmentRows.length);

  vlanTableBody.innerHTML = vlanRows.length
    ? vlanPaged.rows
        .map((item) =>
          tableRow([
            item.vlan_label,
            item.region,
            item.reported_linode_count,
            item.attached_linode_count,
          ])
        )
        .join("")
    : `<tr><td class="empty" colspan="4">No VLANs match your filter.</td></tr>`;

  attachmentTableBody.innerHTML = attachmentRows.length
    ? attachmentPaged.rows
        .map((item) =>
          tableRow([
            item.vlan_label,
            item.region,
            `${item.linode_label} (${item.linode_id})`,
            item.ipam_address || "-",
            item.source,
            item.config_id,
          ])
        )
        .join("")
    : `<tr><td class="empty" colspan="6">No attachments match your filter.</td></tr>`;

  renderPagination(
    vlanPagination,
    vlanPaged.page,
    vlanPaged.totalPages,
    () => {
      vlanPage -= 1;
      renderTables(data);
    },
    () => {
      vlanPage += 1;
      renderTables(data);
    }
  );

  renderPagination(
    attachmentPagination,
    attachmentPaged.page,
    attachmentPaged.totalPages,
    () => {
      attachmentPage -= 1;
      renderTables(data);
    },
    () => {
      attachmentPage += 1;
      renderTables(data);
    }
  );
}

async function refresh() {
  try {
    const response = await fetch("/api/topology", { cache: "no-store" });
    if (!response.ok) {
      throw new Error(`HTTP ${response.status}`);
    }
    latest = await response.json();
    renderCards(latest);
    renderTables(latest);
    const fetchStatus = latest.ui?.status === "ok" && latest.scrape.success === 1;
    const statusText = fetchStatus ? "Live" : `Degraded: ${latest.ui?.error || "scrape not successful"}`;
    setStatus(fetchStatus, statusText);
    lastUpdate.textContent = new Date().toLocaleTimeString();
  } catch (error) {
    setStatus(false, `Connection error: ${error.message}`);
    lastUpdate.textContent = new Date().toLocaleTimeString();
  }
}

vlanSearchInput.addEventListener("input", () => {
  vlanPage = 1;
  if (latest) {
    renderTables(latest);
  }
});

attachmentSearchInput.addEventListener("input", () => {
  attachmentPage = 1;
  if (latest) {
    renderTables(latest);
  }
});

vlanPageSize.addEventListener("change", () => {
  vlanPage = 1;
  if (latest) {
    renderTables(latest);
  }
});

attachmentPageSize.addEventListener("change", () => {
  attachmentPage = 1;
  if (latest) {
    renderTables(latest);
  }
});

vlanFilterToggle.addEventListener("click", () => {
  const isHidden = vlanFilterRow.classList.toggle("hidden");
  vlanFilterToggle.classList.toggle("active", !isHidden);
  if (!isHidden) {
    vlanSearchInput.focus();
    return;
  }
  vlanSearchInput.value = "";
  vlanPage = 1;
  if (latest) {
    renderTables(latest);
  }
});

attachmentFilterToggle.addEventListener("click", () => {
  const isHidden = attachmentFilterRow.classList.toggle("hidden");
  attachmentFilterToggle.classList.toggle("active", !isHidden);
  if (!isHidden) {
    attachmentSearchInput.focus();
    return;
  }
  attachmentSearchInput.value = "";
  attachmentPage = 1;
  if (latest) {
    renderTables(latest);
  }
});

if (themeToggle) {
  themeToggle.addEventListener("click", () => {
    const nextTheme = document.body.classList.contains("dark") ? "light" : "dark";
    localStorage.setItem("topology-ui-theme", nextTheme);
    applyTheme(nextTheme);
  });
}

initializeTheme();
refresh();
setInterval(refresh, refreshSeconds * 1000);
