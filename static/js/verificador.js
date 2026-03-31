/**
 * verificador.js
 * ─────────────
 * Lógica del formulario de verificación de pedidos.
 *
 * Depende de:
 *   CATALOG         — array de productos inyectado por Jinja desde catalog.py
 *   DELIVERY_OPTIONS — objeto de opciones de entrega inyectado por Jinja
 *
 * Funcionalidades:
 *   - Agregar filas de producto dinámicamente
 *   - Selector de variante que se activa según el producto elegido
 *   - Cálculo en vivo del subtotal y total estimado
 *   - Botón para duplicar una línea de producto
 *   - Botón para eliminar líneas
 */

/* ─── Estado ────────────────────────────────────────────────── */
let rowCount = 0;

/* ─── Utilidades del catálogo ───────────────────────────────── */

/**
 * Busca un producto en el catálogo por su ID.
 */
function findProduct(productId) {
  return CATALOG.find((p) => p.id === productId) || null;
}

/**
 * Devuelve el precio_web de una variante si aplica,
 * o del producto si es simple.
 */
function getPrecioWeb(productId, variantId) {
  const product = findProduct(productId);
  if (!product) return 0;
  if (product.type === "simple") return product.precio_web || 0;
  const variant = (product.variants || []).find((v) => v.id === variantId);
  return variant ? variant.precio_web || 0 : 0;
}

/**
 * Devuelve el costo de envío para el tipo de entrega seleccionado.
 */
function getEnvioCost(tipoEntrega) {
  const opt = DELIVERY_OPTIONS[tipoEntrega];
  return opt ? opt.cost || 0 : 0;
}

/* ─── Creación de filas ─────────────────────────────────────── */

/**
 * Agrega una nueva fila de producto a la tabla.
 * Si `cloneData` se pasa, pre-llena los valores (para duplicar).
 */
function addProductRow(cloneData = null) {
  rowCount++;
  const rowId = `row-${rowCount}`;
  const tbody = document.getElementById("productRows");

  const tr = document.createElement("tr");
  tr.id = rowId;
  tr.className = "product-row align-middle";

  // Opciones del select de productos
  let productOptions = `<option value="">Selecciona producto...</option>`;
  CATALOG.forEach((p) => {
    const selected = cloneData && cloneData.productId === p.id ? "selected" : "";
    productOptions += `<option value="${p.id}" ${selected}>${p.name}</option>`;
  });

  tr.innerHTML = `
    <td>
      <select name="product_id[]"
              class="form-select form-select-sm product-select"
              data-row="${rowId}"
              onchange="onProductChange(this)"
              required>
        ${productOptions}
      </select>
    </td>
    <td>
      <select name="variant_id[]"
              class="form-select form-select-sm variant-select"
              data-row="${rowId}"
              id="variant-${rowId}"
              onchange="updateRowTotal('${rowId}')">
        <option value="">—</option>
      </select>
    </td>
    <td>
      <input type="number" name="quantity[]"
             class="form-control form-control-sm quantity-input"
             data-row="${rowId}"
             value="${cloneData ? cloneData.quantity : 1}"
             min="1" step="1"
             style="width:70px"
             onchange="updateRowTotal('${rowId}')"
             oninput="updateRowTotal('${rowId}')"/>
    </td>
    <td>
      <span class="precio-web-display text-primary fw-medium" id="pw-${rowId}">$0.00</span>
    </td>
    <td>
      <span class="precio-tienda-display text-muted small" id="pt-${rowId}">$0.00</span>
    </td>
    <td>
      <span class="subtotal-display fw-semibold" id="sub-${rowId}">$0.00</span>
    </td>
    <td class="text-center">
      <div class="d-flex gap-1 flex-nowrap">
        <button type="button"
                class="btn btn-sm btn-outline-secondary"
                title="Duplicar línea"
                onclick="duplicateRow('${rowId}')">
          <i class="bi bi-files"></i>
        </button>
        <button type="button"
                class="btn btn-sm btn-remove-row"
                title="Eliminar"
                onclick="removeRow('${rowId}')">
          <i class="bi bi-trash3"></i>
        </button>
      </div>
    </td>
  `;

  tbody.appendChild(tr);

  // Si se clonó, restaurar variante y recalcular
  if (cloneData && cloneData.productId) {
    const selectEl = tr.querySelector(".product-select");
    populateVariants(selectEl, cloneData.productId, cloneData.variantId);
    updateRowTotal(rowId);
  }

  updateLiveTotals();
  return rowId;
}

/* ─── Eventos de selección ──────────────────────────────────── */

/**
 * Llamado al cambiar el producto seleccionado en una fila.
 */
function onProductChange(selectEl) {
  const rowId    = selectEl.dataset.row;
  const productId = selectEl.value;
  populateVariants(selectEl, productId, null);
  updateRowTotal(rowId);
}

/**
 * Llena el select de variantes para la fila según el producto.
 */
function populateVariants(productSelect, productId, selectedVariantId) {
  const rowId  = productSelect.dataset.row;
  const varSel = document.getElementById(`variant-${rowId}`);
  if (!varSel) return;

  const product = findProduct(productId);

  if (!product || product.type === "simple" || !product.variants?.length) {
    varSel.innerHTML = `<option value="">—</option>`;
    varSel.disabled = true;
  } else {
    let opts = `<option value="">Elige variante...</option>`;
    product.variants.forEach((v) => {
      const sel = selectedVariantId === v.id ? "selected" : "";
      opts += `<option value="${v.id}" ${sel}>${v.label} — $${v.precio_web}</option>`;
    });
    varSel.innerHTML = opts;
    varSel.disabled = false;
  }
}

/* ─── Cálculo de subtotales por fila ────────────────────────── */

/**
 * Actualiza los displays de precio y subtotal de una fila.
 */
function updateRowTotal(rowId) {
  const row = document.getElementById(rowId);
  if (!row) return;

  const productId = row.querySelector(".product-select")?.value || "";
  const variantId = row.querySelector(".variant-select")?.value || "";
  const qty       = parseInt(row.querySelector(".quantity-input")?.value || "1", 10);

  const product   = findProduct(productId);
  let precioWeb   = 0;
  let precioTienda = 0;

  if (product) {
    if (product.type === "simple") {
      precioWeb    = product.precio_web || 0;
      precioTienda = product.precio_tienda || 0;
    } else {
      const variant = (product.variants || []).find((v) => v.id === variantId);
      if (variant) {
        precioWeb    = variant.precio_web || 0;
        precioTienda = variant.precio_tienda || 0;
      }
    }
  }

  const subtotal = precioWeb * qty;

  const pwEl  = document.getElementById(`pw-${rowId}`);
  const ptEl  = document.getElementById(`pt-${rowId}`);
  const subEl = document.getElementById(`sub-${rowId}`);

  if (pwEl)  pwEl.textContent  = formatMoney(precioWeb);
  if (ptEl)  ptEl.textContent  = formatMoney(precioTienda);
  if (subEl) subEl.textContent = formatMoney(subtotal);

  updateLiveTotals();
}

/* ─── Cálculo global en vivo ────────────────────────────────── */

/**
 * Recalcula el subtotal total sumando todas las filas,
 * y muestra el preview del total con envío y diferencia.
 */
function updateLiveTotals() {
  let totalWeb = 0;
  const rows = document.querySelectorAll(".product-row");

  rows.forEach((row) => {
    const rowId    = row.id;
    const productId = row.querySelector(".product-select")?.value || "";
    const variantId = row.querySelector(".variant-select")?.value || "";
    const qty       = parseInt(row.querySelector(".quantity-input")?.value || "1", 10);

    totalWeb += getPrecioWeb(productId, variantId) * qty;
  });

  // Header subtotal
  const liveSubEl = document.getElementById("liveSubtotalWeb");
  if (liveSubEl) liveSubEl.textContent = formatMoney(totalWeb);

  // Preview card
  const tipoEntrega    = document.getElementById("tipo_entrega")?.value || "";
  const envioCost      = getEnvioCost(tipoEntrega);
  const totalEstimado  = totalWeb + envioCost;
  const totalReportado = parseFloat(document.getElementById("total_reportado")?.value || 0) || 0;
  const diferencia     = totalReportado - totalEstimado;

  const preview = document.getElementById("livePreview");
  if (preview) {
    if (rows.length > 0 && totalWeb > 0) {
      preview.classList.remove("d-none");
    }

    const previewSubEl   = document.getElementById("previewSubtotal");
    const previewEnvEl   = document.getElementById("previewEnvio");
    const previewTotEl   = document.getElementById("previewTotal");
    const previewDiffEl  = document.getElementById("previewDiff");

    if (previewSubEl)  previewSubEl.textContent  = formatMoney(totalWeb);
    if (previewEnvEl)  previewEnvEl.textContent  = formatMoney(envioCost);
    if (previewTotEl)  previewTotEl.textContent  = formatMoney(totalEstimado);

    if (previewDiffEl && totalReportado > 0) {
      const diffText = (diferencia >= 0 ? "+" : "") + formatMoney(diferencia);
      previewDiffEl.textContent = diffText;
      previewDiffEl.className   = "fw-bold " + (
        Math.abs(diferencia) <= 0.01 ? "text-success" :
        Math.abs(diferencia) <= 5    ? "text-warning" :
                                       "text-danger"
      );
    } else if (previewDiffEl) {
      previewDiffEl.textContent = "—";
    }
  }

  // Hint de envío bajo el select
  const hint = document.getElementById("envio_hint");
  if (hint && tipoEntrega) {
    const opt = DELIVERY_OPTIONS[tipoEntrega];
    hint.textContent = opt
      ? `Envío real: $${opt.cost} MXN`
      : "";
  }
}

/* ─── Eliminar y duplicar filas ─────────────────────────────── */

function removeRow(rowId) {
  const row = document.getElementById(rowId);
  if (row) {
    row.style.animation = "slideIn 0.2s ease reverse";
    setTimeout(() => {
      row.remove();
      updateLiveTotals();
    }, 180);
  }
}

function duplicateRow(rowId) {
  const row = document.getElementById(rowId);
  if (!row) return;
  const productId = row.querySelector(".product-select")?.value || "";
  const variantId = row.querySelector(".variant-select")?.value || "";
  const quantity  = parseInt(row.querySelector(".quantity-input")?.value || "1", 10);
  addProductRow({ productId, variantId, quantity });
}

/* ─── Formateo ──────────────────────────────────────────────── */

function formatMoney(value) {
  return "$" + parseFloat(value || 0).toFixed(2).replace(/\B(?=(\d{3})+(?!\d))/g, ",");
}

/* ─── Inicialización ────────────────────────────────────────── */

document.addEventListener("DOMContentLoaded", () => {
  // Agregar 1 fila vacía al cargar
  addProductRow();

  // Escuchar cambios en tipo de entrega y total reportado para preview en vivo
  const tipoEntregaEl = document.getElementById("tipo_entrega");
  if (tipoEntregaEl) {
    tipoEntregaEl.addEventListener("change", updateLiveTotals);
  }

  const totalRepEl = document.getElementById("total_reportado");
  if (totalRepEl) {
    totalRepEl.addEventListener("input", updateLiveTotals);
  }
});
