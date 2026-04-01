/**
 * revisar.js
 * ──────────
 * Lógica para la página de revisión/corrección del pedido detectado.
 *
 * Depende de CATALOG y DELIVERY_OPTIONS inyectados por Jinja.
 */

let rowCounter = 1000; // offset para no chocar con ids auto-generados por Jinja

/* ─── Utilidades del catálogo ──────────────────────────────── */

function findProduct(pid) {
  return CATALOG.find(p => p.id === pid) || null;
}

function getPrecioWeb(pid, vid) {
  const p = findProduct(pid);
  if (!p) return 0;
  if (p.type === "simple") return p.precio_web || 0;
  const v = (p.variants || []).find(v => v.id === vid);
  return v ? (v.precio_web || 0) : 0;
}

function getPrecioTienda(pid, vid) {
  const p = findProduct(pid);
  if (!p) return 0;
  if (p.type === "simple") return p.precio_tienda || 0;
  const v = (p.variants || []).find(v => v.id === vid);
  return v ? (v.precio_tienda || 0) : 0;
}

function fmt(n) {
  return "$" + parseFloat(n || 0).toFixed(2).replace(/\B(?=(\d{3})+(?!\d))/g, ",");
}

/* ─── Poblar variantes ─────────────────────────────────────── */

/**
 * Genera las opciones de variante para un select dado un producto.
 * keepCurrent: si true, intenta mantener el valor ya seleccionado.
 */
function populateVariants(productSelect, keepCurrent = false) {
  const rowId  = productSelect.dataset.row;
  const pid    = productSelect.value;
  const varSel = document.getElementById(`variant-${rowId}`);
  if (!varSel) return;

  const prevVal = keepCurrent ? varSel.value : "";
  const product = findProduct(pid);

  if (!product || product.type === "simple" || !product.variants?.length) {
    varSel.innerHTML = `<option value="">—</option>`;
    varSel.disabled = true;
  } else {
    let opts = `<option value="">Elige variante...</option>`;
    product.variants.forEach(v => {
      const sel = prevVal === v.id ? "selected" : "";
      opts += `<option value="${v.id}" ${sel}>${v.label} — $${v.precio_web}</option>`;
    });
    varSel.innerHTML = opts;
    varSel.disabled = false;
  }

  updateRowDisplay(rowId);
}

/* ─── Evento: cambio de producto ───────────────────────────── */

function onProductChange(selectEl) {
  populateVariants(selectEl, false);
}

/* ─── Actualizar display de precios de una fila ────────────── */

function updateRowDisplay(rowId) {
  const row = document.getElementById(rowId);
  if (!row) return;

  const pid = row.querySelector(".product-select")?.value || "";
  const vid = row.querySelector(".variant-select")?.value || "";
  const qty = parseInt(row.querySelector(".quantity-input")?.value || "1", 10);

  const pw  = getPrecioWeb(pid, vid);
  const pt  = getPrecioTienda(pid, vid);
  const sub = pw * qty;

  const pwEl  = document.getElementById(`pw-${rowId}`);
  const ptEl  = document.getElementById(`pt-${rowId}`);
  const subEl = document.getElementById(`sub-${rowId}`);

  if (pwEl)  pwEl.textContent  = fmt(pw);
  if (ptEl)  ptEl.textContent  = fmt(pt);
  if (subEl) subEl.textContent = fmt(sub);

  recalcAllRows();
}

/* ─── Recalcular subtotal total ────────────────────────────── */

function recalcAllRows() {
  let total = 0;
  document.querySelectorAll(".item-row").forEach(row => {
    const rowId = row.id;
    const pid = row.querySelector(".product-select")?.value || "";
    const vid = row.querySelector(".variant-select")?.value || "";
    const qty = parseInt(row.querySelector(".quantity-input")?.value || "1", 10);
    total += getPrecioWeb(pid, vid) * qty;
  });

  const el = document.getElementById("liveSubtotal");
  if (el) el.textContent = fmt(total);
}

/* ─── Eliminar fila ────────────────────────────────────────── */

function removeRow(rowId) {
  // Eliminar la fila de warning debajo si existe
  const warningNext = document.querySelector(`#${CSS.escape(rowId)} + .table-warning-hint`);
  if (warningNext) warningNext.remove();

  const row = document.getElementById(rowId);
  if (row) {
    row.style.transition = "opacity 0.15s";
    row.style.opacity = "0";
    setTimeout(() => { row.remove(); recalcAllRows(); }, 150);
  }
}

/* ─── Agregar fila manual ──────────────────────────────────── */

function addManualRow() {
  rowCounter++;
  const rowId = `row-manual-${rowCounter}`;
  const tbody = document.getElementById("itemRows");

  // Construir opciones de producto
  let productOpts = `<option value="">Selecciona producto...</option>`;
  CATALOG.forEach(p => {
    productOpts += `<option value="${p.id}">${p.name}</option>`;
  });

  const tr = document.createElement("tr");
  tr.id = rowId;
  tr.className = "item-row";
  tr.style.animation = "slideIn 0.25s ease";
  tr.innerHTML = `
    <td>
      <select name="product_id[]"
              class="form-select form-select-sm product-select"
              data-row="${rowId}"
              onchange="onProductChange(this)"
              required>
        ${productOpts}
      </select>
      <input type="hidden" name="product_name[]" value=""/>
    </td>
    <td>
      <select name="variant_id[]"
              class="form-select form-select-sm variant-select"
              data-row="${rowId}"
              id="variant-${rowId}"
              onchange="updateRowDisplay('${rowId}')">
        <option value="">—</option>
      </select>
      <input type="hidden" name="variant_label[]" value=""/>
    </td>
    <td>
      <input type="number" name="quantity[]"
             class="form-control form-control-sm quantity-input"
             data-row="${rowId}"
             value="1" min="1" step="1" style="width:70px"
             oninput="updateRowDisplay('${rowId}')"/>
    </td>
    <td><span class="price-web text-primary fw-medium" id="pw-${rowId}">$0.00</span></td>
    <td><span class="price-tienda text-muted small" id="pt-${rowId}">$0.00</span></td>
    <td><span class="subtotal-web fw-semibold" id="sub-${rowId}">$0.00</span></td>
    <td><span class="badge badge-conf-high">manual</span></td>
    <td class="text-center">
      <button type="button" class="btn btn-sm btn-remove-row"
              onclick="removeRow('${rowId}')">
        <i class="bi bi-trash3"></i>
      </button>
    </td>
  `;

  tbody.appendChild(tr);
}
