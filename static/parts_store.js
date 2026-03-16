const API = {
  meta: '/api/parts-store/meta',
  searchParts: (q='') => `/api/parts-store/search-parts?q=${encodeURIComponent(q)}`,
  searchCustomers: (q='') => `/api/parts-store/search-customers?q=${encodeURIComponent(q)}`,
  checkout: '/api/parts-store/checkout',
  partDetails: (id) => `/api/parts-store/part-details/${id}`,
  customerHistory: (id) => `/api/parts-store/customer-history/${id}`,
  repeatInvoice: (id) => `/api/parts-store/repeat-invoice/${id}`,
};

const $ = (id) => document.getElementById(id);

const state = {
  parts: [],
  cart: [],
  customerMode: 'EXISTING',
  selectedCustomer: null,
  zelleEmail: 'yaidelp@yahoo.com',
  activePart: null,
  activePartDetails: null,
  customerHistory: null,
};

function readToken() {
  return (
    localStorage.getItem('token') ||
    localStorage.getItem('access_token') ||
    sessionStorage.getItem('token') ||
    sessionStorage.getItem('access_token') ||
    ''
  ).trim();
}

function readTokenType() {
  return (localStorage.getItem('token_type') || sessionStorage.getItem('token_type') || 'bearer').trim();
}

function getAuthHeaders() {
  const token = readToken();
  if (!token) return {};
  const schemeRaw = readTokenType();
  const scheme = schemeRaw ? schemeRaw[0].toUpperCase() + schemeRaw.slice(1).toLowerCase() : 'Bearer';
  return { Authorization: `${scheme} ${token}` };
}

async function apiGet(url) {
  const res = await fetch(url, { headers: { ...getAuthHeaders() } });
  if (res.status === 401) {
    window.location.href = '/static/index.html';
    return null;
  }
  if (!res.ok) throw new Error(await res.text());
  return await res.json();
}

async function apiSend(url, method, payload) {
  const res = await fetch(url, {
    method,
    headers: { 'Content-Type': 'application/json', ...getAuthHeaders() },
    body: JSON.stringify(payload),
  });
  if (res.status === 401) {
    window.location.href = '/static/index.html';
    return null;
  }
  if (!res.ok) throw new Error(await res.text());
  return await res.json();
}

function money(v) {
  const n = Number(v || 0);
  return `$${n.toFixed(2)}`;
}

function showMsg(text, isError = false) {
  const box = $('posMsg');
  box.className = `msg ${isError ? 'err' : 'ok'}`;
  box.style.display = 'block';
  box.innerHTML = text;
}

function clearMsg() {
  const box = $('posMsg');
  box.className = 'msg';
  box.style.display = 'none';
  box.textContent = '';
}

function stockClass(qty) {
  const n = Number(qty || 0);
  if (n <= 0) return 'out';
  if (n <= 3) return 'low';
  return 'ok';
}


function productImagePlaceholder(label = 'No image available') {
  return `<div class="no-image-box">${label}</div>`;
}

function safeImageMarkup(url, alt = '', cssClass = '') {
  if (!url) return productImagePlaceholder();
  return `<img src="${url}" alt="${alt}" class="${cssClass}" data-fallback-image="1" />`;
}

function applyImageFallbacks(root = document) {
  root.querySelectorAll('[data-fallback-image="1"]').forEach((img) => {
    img.addEventListener('error', () => {
      const wrapper = img.closest('.product-media, .modal-main-image, .modal-thumb');
      if (!wrapper) {
        img.remove();
        return;
      }
      if (wrapper.classList.contains('modal-thumb')) {
        wrapper.remove();
        return;
      }
      wrapper.innerHTML = productImagePlaceholder();
    }, { once: true });
  });
}

function publicPartLines(part) {
  const fitment = [part.vehicle_make, part.vehicle_model].filter(Boolean).join(' ');
  const years = part.year_from || part.year_to
    ? [part.year_from || '-', part.year_to || '-'].join(' to ')
    : '';
  return [
    ['Code', part.part_code || '-'],
    ['Brand', part.brand || '-'],
    ['Category', part.category || '-'],
    ['Sub Category', part.sub_category || '-'],
    ['OEM', part.oem_reference || '-'],
    ['Engine', part.engine_type || '-'],
    ['Fitment', fitment || '-'],
    ['Years', years || '-'],
    ['Stock', String(part.quantity_in_stock ?? 0)],
    ['Taxable', part.taxable ? 'Yes' : 'No'],
  ].filter(([, value]) => value && value !== '-');
}

function closeProductModal() {
  $('productModal').classList.add('hidden');
  state.activePart = null;
  state.activePartDetails = null;
}

function selectModalImage(url, altText = '') {
  const box = $('modalMainImage');
  box.innerHTML = url ? `<img src="${url}" alt="${altText || ''}" data-fallback-image="1" />` : productImagePlaceholder();
  applyImageFallbacks(box);
}

function renderProductModal(details) {
  state.activePartDetails = details;
  $('modalPartName').textContent = details.part_name || 'Part Details';
  $('modalPartPrice').textContent = money(details.sale_price_base);
  $('modalPartCode').textContent = details.part_code || '-';

  const info = publicPartLines(details).map(([label, value]) => `
    <div class="detail-row"><span>${label}</span><strong>${value}</strong></div>
  `).join('');
  $('modalPartInfo').innerHTML = info;

  const desc = [details.description, details.technical_notes].filter(Boolean).join('\n\n');
  $('modalPartDescription').textContent = desc || 'No additional public details for this item.';

  const images = Array.isArray(details.images) ? details.images.filter(x => x && x.image_url) : [];
  const primary = images[0]?.image_url || details.primary_image_url || null;
  selectModalImage(primary, details.part_name || '');

  const thumbs = $('modalThumbs');
  if (!images.length) {
    thumbs.innerHTML = `<div class="no-image-box small">No photos loaded</div>`;
  } else {
    thumbs.innerHTML = images.map((img, idx) => `
      <button class="modal-thumb ${idx === 0 ? 'active' : ''}" type="button" data-modal-img="${img.image_url}" data-modal-alt="${img.alt_text || details.part_name || ''}">
        <img src="${img.image_url}" alt="${img.alt_text || details.part_name || ''}" data-fallback-image="1" />
      </button>
    `).join('');
    thumbs.querySelectorAll('[data-modal-img]').forEach((btn) => {
      btn.addEventListener('click', () => {
        thumbs.querySelectorAll('.modal-thumb').forEach((x) => x.classList.remove('active'));
        btn.classList.add('active');
        selectModalImage(btn.dataset.modalImg, btn.dataset.modalAlt || '');
      });
    });
  }

  $('modalAddBtn').onclick = () => {
    addToCart(details.id);
    closeProductModal();
  };

  $('productModal').classList.remove('hidden');
  applyImageFallbacks($('productModal'));
}

async function openProductModal(id) {
  const part = state.parts.find((x) => Number(x.id) === Number(id));
  state.activePart = part || null;
  $('modalPartName').textContent = part?.part_name || 'Loading...';
  $('modalPartPrice').textContent = part ? money(part.sale_price_base) : '$0.00';
  $('modalPartCode').textContent = part?.part_code || '-';
  $('modalPartInfo').innerHTML = '<div class="hint">Loading item details...</div>';
  $('modalPartDescription').textContent = '';
  $('modalThumbs').innerHTML = '';
  $('modalMainImage').innerHTML = productImagePlaceholder();
  $('productModal').classList.remove('hidden');

  try {
    const details = await apiGet(API.partDetails(id));
    if (!details) return;
    renderProductModal(details);
  } catch (err) {
    console.error(err);
    $('modalPartInfo').innerHTML = '<div class="hint">Could not load item details.</div>';
  }
}

function renderParts(list) {
  const grid = $('partsGrid');
  if (!list.length) {
    grid.innerHTML = '<div class="hint">No parts found.</div>';
    return;
  }

  grid.innerHTML = list.map((p) => {
    const media = safeImageMarkup(p.primary_image_url, p.part_name || '', 'product-main-image');
    return `
      <article class="card product" data-view-id="${p.id}">
        <div class="product-media" data-view-id="${p.id}">${media}</div>
        <div class="product-body">
          <span class="pill">${p.brand || 'No brand'}</span>
          <div class="product-name" data-view-id="${p.id}">${p.part_name || '-'}</div>
          <div class="product-meta">
            <div><strong>Code:</strong> ${p.part_code || '-'}</div>
            <div><strong>OEM:</strong> ${p.oem_reference || '-'}</div>
            <div class="stock ${stockClass(p.quantity_in_stock)}">Stock: ${p.quantity_in_stock ?? 0}</div>
          </div>
          <div class="price-row">
            <div class="price">${money(p.sale_price_base)}</div>
            <div style="display:flex; gap:8px; flex-wrap:wrap;">
              <button class="btn btn-ghost btn-sm" type="button" data-view-id="${p.id}">View</button>
              <button class="btn btn-primary btn-sm" type="button" data-add-id="${p.id}">Add to Cart</button>
            </div>
          </div>
        </div>
      </article>
    `;
  }).join('');

  grid.querySelectorAll('[data-add-id]').forEach((btn) => {
    btn.addEventListener('click', (e) => {
      e.stopPropagation();
      addToCart(Number(btn.dataset.addId));
    });
  });

  grid.querySelectorAll('[data-view-id]').forEach((el) => {
    el.addEventListener('click', (e) => {
      e.stopPropagation();
      openProductModal(Number(el.dataset.viewId));
    });
  });

  applyImageFallbacks(grid);
}

function addToCart(id) {
  const part = state.parts.find((x) => Number(x.id) === Number(id));
  if (!part) return;
  if (Number(part.quantity_in_stock || 0) <= 0) {
    showMsg('This item is out of stock.', true);
    return;
  }

  const existing = state.cart.find((x) => Number(x.id) === Number(id));
  if (existing) {
    if (existing.qty + 1 > Number(part.quantity_in_stock || 0)) {
      showMsg('Cannot add more than current stock.', true);
      return;
    }
    existing.qty += 1;
  } else {
    state.cart.push({ ...part, qty: 1, unit_price: Number(part.sale_price_base || 0), base_price: Number(part.sale_price_base || 0) });
  }
  clearMsg();
  renderCart();
}

function updateQty(id, delta) {
  const row = state.cart.find((x) => Number(x.id) === Number(id));
  if (!row) return;
  const next = row.qty + delta;
  if (next <= 0) {
    state.cart = state.cart.filter((x) => Number(x.id) !== Number(id));
  } else if (next <= Number(row.quantity_in_stock || 0)) {
    row.qty = next;
  }
  renderCart();
}

function removeCart(id) {
  state.cart = state.cart.filter((x) => Number(x.id) !== Number(id));
  renderCart();
}

function updateUnitPrice(id, value) {
  const row = state.cart.find((x) => Number(x.id) === Number(id));
  if (!row) return;

  let price = Number(value);
  if (!Number.isFinite(price) || price < 0) {
    price = Number(row.unit_price ?? row.sale_price_base ?? 0);
  }
  row.unit_price = Number(price.toFixed(2));
  renderCart();
}

function calcTotals() {
  const paymentMethod = $('paymentMethod').value;
  const cashTaxable = $('cashTaxable').value === 'true';

  let subtotal = 0;
  let taxableSubtotal = 0;

  state.cart.forEach((row) => {
    const line = Number(row.unit_price ?? row.sale_price_base ?? 0) * Number(row.qty || 0);
    subtotal += line;
    if (row.taxable) taxableSubtotal += line;
  });

  let tax = 0;
  let fee = 0;

  if (paymentMethod === 'CASH') {
    tax = cashTaxable ? taxableSubtotal * 0.07 : 0;
  } else if (paymentMethod === 'CARD') {
    tax = taxableSubtotal * 0.07;
    fee = (subtotal + tax) * 0.04;
  } else {
    tax = taxableSubtotal * 0.07;
  }

  const total = subtotal + tax + fee;
  return { subtotal, tax, fee, total };
}

function renderCart() {
  const box = $('cartList');
  const empty = $('cartEmpty');
  if (!state.cart.length) {
    box.innerHTML = '';
    empty.style.display = 'block';
  } else {
    empty.style.display = 'none';
    box.innerHTML = state.cart.map((row) => {
      const currentPrice = Number(row.unit_price ?? row.sale_price_base ?? 0);
      const basePrice = Number(row.base_price ?? row.sale_price_base ?? 0);
      const lineTotal = currentPrice * Number(row.qty || 0);
      const changed = Math.abs(currentPrice - basePrice) > 0.0001;
      return `
      <div class="cart-item">
        <div>
          <div class="cart-name">${row.part_name}</div>
          <div class="cart-code">${row.part_code} · Base: ${money(basePrice)}</div>
          <div class="price-editor">
            <div>
              <input class="price-input" type="number" min="0" step="0.01" value="${currentPrice.toFixed(2)}" data-price-id="${row.id}" />
              <div class="price-note">${changed ? 'Custom sold price saved for this sale.' : 'Using inventory sale price.'}</div>
            </div>
            <div class="line-total">${money(lineTotal)}</div>
          </div>
        </div>
        <div class="cart-controls">
          <button class="btn btn-secondary btn-sm" type="button" data-qty="-1" data-id="${row.id}">-</button>
          <span class="qty-badge">${row.qty}</span>
          <button class="btn btn-secondary btn-sm" type="button" data-qty="1" data-id="${row.id}">+</button>
          <button class="btn btn-ghost btn-sm" type="button" data-remove-id="${row.id}">Remove</button>
        </div>
      </div>
    `}).join('');

    box.querySelectorAll('[data-qty]').forEach((btn) => {
      btn.addEventListener('click', () => updateQty(Number(btn.dataset.id), Number(btn.dataset.qty)));
    });
    box.querySelectorAll('[data-remove-id]').forEach((btn) => {
      btn.addEventListener('click', () => removeCart(Number(btn.dataset.removeId)));
    });
    box.querySelectorAll('[data-price-id]').forEach((input) => {
      input.addEventListener('change', () => updateUnitPrice(Number(input.dataset.priceId), input.value));
      input.addEventListener('blur', () => updateUnitPrice(Number(input.dataset.priceId), input.value));
    });
  }

  const totals = calcTotals();
  $('subtotalValue').textContent = money(totals.subtotal);
  $('taxValue').textContent = money(totals.tax);
  $('feeValue').textContent = money(totals.fee);
  $('totalValue').textContent = money(totals.total);
}


async function openInvoicePdf(url){
  try{
    const res = await fetch(url, {headers:{...getAuthHeaders()}});
    if(res.status === 401){
      window.location.href = '/static/index.html';
      return;
    }
    if(!res.ok) throw new Error('Could not load PDF');
    const blob = await res.blob();
    const fileURL = URL.createObjectURL(blob);
    window.open(fileURL, '_blank');
    window.setTimeout(() => URL.revokeObjectURL(fileURL), 60000);
  }catch(err){
    console.error(err);
    showMsg('Failed to open invoice PDF.', true);
  }
}

function addHistoryInvoiceToCart(invoice){
  if (!invoice || !Array.isArray(invoice.items) || !invoice.items.length) return;

  for (const src of invoice.items) {
    if (!src.inventory_item_id) continue;
    const part = state.parts.find((x) => Number(x.id) === Number(src.inventory_item_id));
    if (!part || Number(part.quantity_in_stock || 0) <= 0) continue;

    const existing = state.cart.find((x) => Number(x.id) === Number(part.id));
    const qtyToAdd = Math.max(1, Number(src.qty || 1));

    if (existing) {
      existing.qty = Math.min(Number(part.quantity_in_stock || 0), existing.qty + qtyToAdd);
      existing.unit_price = Number(src.unit_price ?? existing.unit_price ?? part.sale_price_base ?? 0);
    } else {
      state.cart.push({
        ...part,
        qty: Math.min(Number(part.quantity_in_stock || 0), qtyToAdd),
        unit_price: Number(src.unit_price ?? part.sale_price_base ?? 0),
        base_price: Number(part.sale_price_base ?? 0),
      });
    }
  }

  renderCart();
  clearMsg();
}

function renderCustomerHistoryPanel(data){
  const empty = $('customerHistoryEmpty');
  const body = $('customerHistoryBody');
  if (!body || !empty) return;

  if (!data || !Array.isArray(data.recent_invoices) || !data.recent_invoices.length) {
    body.innerHTML = '';
    empty.textContent = 'No purchase history yet for this customer.';
    empty.style.display = 'block';
    return;
  }

  empty.style.display = 'none';

  const recs = Array.isArray(data.recommendations) ? data.recommendations : [];
  const recHtml = recs.length ? `
    <div class="history-block">
      <div class="history-title">Recommended based on history</div>
      <div class="history-tags">
        ${recs.map((r) => `<button type="button" class="history-tag" data-rec-item-id="${r.inventory_item_id}">${r.description} <small>×${r.times}</small></button>`).join('')}
      </div>
    </div>
  ` : '';

  const invoiceHtml = data.recent_invoices.map((inv) => `
    <div class="history-invoice">
      <div class="history-invoice-head">
        <div>
          <div class="history-invoice-no">${inv.invoice_number}</div>
          <div class="hint">${inv.created_at_label} · ${inv.payment_method || '-'} · ${money(inv.total)}</div>
        </div>
        <button class="btn btn-secondary btn-sm" type="button" data-repeat-invoice-id="${inv.invoice_id}">Repeat Sale</button>
      </div>
      <div class="history-lines">
        ${inv.items.map((it) => `<div class="history-line">${it.description} <span>Qty ${it.qty}</span></div>`).join('')}
      </div>
    </div>
  `).join('');

  body.innerHTML = recHtml + `<div class="history-block"><div class="history-title">Recent purchases</div>${invoiceHtml}</div>`;

  body.querySelectorAll('[data-repeat-invoice-id]').forEach((btn) => {
    btn.addEventListener('click', () => {
      const invoice = data.recent_invoices.find((x) => Number(x.invoice_id) === Number(btn.dataset.repeatInvoiceId));
      addHistoryInvoiceToCart(invoice);
      showMsg(`Added items from ${invoice.invoice_number} to cart.`);
    });
  });

  body.querySelectorAll('[data-rec-item-id]').forEach((btn) => {
    btn.addEventListener('click', () => {
      addToCart(Number(btn.dataset.recItemId));
    });
  });
}

async function loadCustomerHistory(customerId){
  const empty = $('customerHistoryEmpty');
  const body = $('customerHistoryBody');
  if (!body || !empty) return;

  if (!customerId) {
    state.customerHistory = null;
    body.innerHTML = '';
    empty.textContent = 'Select an existing customer to see purchase history and repeat-sale suggestions.';
    empty.style.display = 'block';
    return;
  }

  empty.textContent = 'Loading purchase history...';
  empty.style.display = 'block';
  body.innerHTML = '';

  try {
    const data = await apiGet(API.customerHistory(customerId));
    if (!data) return;
    state.customerHistory = data;
    renderCustomerHistoryPanel(data);
  } catch (err) {
    console.error(err);
    body.innerHTML = '';
    empty.textContent = 'Could not load customer history.';
    empty.style.display = 'block';
  }
}

function renderSelectedCustomer() {
  const box = $('selectedCustomerBox');
  if (state.customerMode === 'WALK_IN') {
    box.innerHTML = 'Customer for invoice: <strong>Walk-in Customer</strong>';
    return;
  }
  if (state.customerMode === 'EXISTING' && state.selectedCustomer) {
    box.innerHTML = `Using existing customer: <strong>${state.selectedCustomer.name}</strong>${state.selectedCustomer.phone ? ` · ${state.selectedCustomer.phone}` : ''}`;
    loadCustomerHistory(state.selectedCustomer.id);
    return;
  }
  if (state.customerMode === 'QUICK') {
    const name = $('quickCustomerName').value.trim();
    const phone = $('quickCustomerPhone').value.trim();
    if (name) {
      box.innerHTML = `Quick customer to create: <strong>${name}</strong>${phone ? ` · ${phone}` : ''}`;
      return;
    }
  }
  if (state.customerMode !== 'EXISTING') loadCustomerHistory(null);
  box.innerHTML = 'No customer selected yet.';
}

function setCustomerMode(mode) {
  state.customerMode = mode;
  if (mode !== 'EXISTING') state.selectedCustomer = null;
  document.querySelectorAll('.mode-tab').forEach((btn) => btn.classList.toggle('active', btn.dataset.mode === mode));
  $('existingCustomerBox').classList.toggle('hidden', mode !== 'EXISTING');
  $('quickCustomerBox').classList.toggle('hidden', mode !== 'QUICK');
  $('walkInBox').classList.toggle('hidden', mode !== 'WALK_IN');
  renderSelectedCustomer();
}

async function loadParts(q = '') {
  const rows = await apiGet(API.searchParts(q));
  if (!rows) return;
  state.parts = rows;
  renderParts(rows);
}

let customerTimer = null;
async function searchCustomers(q) {
  const box = $('customerResults');
  if (!q || q.trim().length < 1) {
    box.innerHTML = '';
    return;
  }
  const rows = await apiGet(API.searchCustomers(q.trim()));
  if (!rows) return;
  box.innerHTML = rows.map((c) => `
    <div class="customer-result ${state.selectedCustomer && state.selectedCustomer.id === c.id ? 'active' : ''}" data-customer-id="${c.id}">
      <div><strong>${c.name}</strong><div class="hint">${c.phone || '-'}${c.email ? ` · ${c.email}` : ''}</div></div>
      <div>Use</div>
    </div>
  `).join('');
  box.querySelectorAll('[data-customer-id]').forEach((el) => {
    el.addEventListener('click', () => {
      const id = Number(el.dataset.customerId);
      state.selectedCustomer = rows.find((x) => x.id === id) || null;
      renderSelectedCustomer();
      searchCustomers(q);
      loadCustomerHistory(id);
    });
  });
}

function updatePaymentUI() {
  const pm = $('paymentMethod').value;
  $('cashTaxBox').classList.toggle('hidden', pm !== 'CASH');
  $('zelleBox').classList.toggle('hidden', pm !== 'ZELLE');
  renderCart();
}

async function checkout() {
  clearMsg();
  if (!state.cart.length) {
    showMsg('Add at least one part to cart.', true);
    return;
  }

  const paymentMethod = $('paymentMethod').value;
  const payload = {
    payment_method: paymentMethod,
    cash_taxable: $('cashTaxable').value === 'true',
    customer_mode: state.customerMode,
    customer_id: state.customerMode === 'EXISTING' ? state.selectedCustomer?.id || null : null,
    quick_customer: state.customerMode === 'QUICK' ? {
      name: $('quickCustomerName').value.trim(),
      phone: $('quickCustomerPhone').value.trim(),
      email: $('quickCustomerEmail').value.trim(),
    } : null,
    notes: $('saleNotes').value.trim(),
    items: state.cart.map((row) => ({ item_id: row.id, qty: row.qty, unit_price: Number(row.unit_price ?? row.sale_price_base ?? 0), base_price: Number(row.base_price ?? row.sale_price_base ?? 0) })),
  };

  if (state.customerMode === 'EXISTING' && !payload.customer_id) {
    showMsg('Select an existing customer or change customer mode.', true);
    return;
  }
  if (state.customerMode === 'QUICK' && !payload.quick_customer.name) {
    showMsg('Quick customer needs at least a name.', true);
    return;
  }

  $('checkoutBtn').disabled = true;
  $('checkoutBtn').textContent = 'Creating Invoice...';
  try {
    const data = await apiSend(API.checkout, 'POST', payload);
    if (!data) return;
    showMsg(`Invoice <strong>${data.invoice_number}</strong> created successfully. Total: <strong>${money(data.total)}</strong>${data.zelle_email ? `<br>Zelle to: <strong>${data.zelle_email}</strong>` : ''}<br><button id="openInvoicePdfBtn" class="btn btn-ghost btn-sm" type="button">Open invoice PDF</button>`);
    const pdfBtn = $('openInvoicePdfBtn');
    if (pdfBtn) pdfBtn.addEventListener('click', () => openInvoicePdf(data.invoice_pdf_url));
    state.cart = [];
    if (state.customerMode === 'QUICK') {
      $('quickCustomerName').value = '';
      $('quickCustomerPhone').value = '';
      $('quickCustomerEmail').value = '';
    }
    if (state.customerMode === 'EXISTING') {
      state.selectedCustomer = null;
      $('customerSearchInput').value = '';
      $('customerResults').innerHTML = '';
    }
    $('saleNotes').value = '';
    renderSelectedCustomer();
    renderCart();
    if (state.selectedCustomer?.id) await loadCustomerHistory(state.selectedCustomer.id);
    await loadParts($('searchInput').value.trim());
  } catch (err) {
    console.error(err);
    showMsg(String(err.message || err), true);
  } finally {
    $('checkoutBtn').disabled = false;
    $('checkoutBtn').textContent = 'Create Invoice';
  }
}

function setupEvents() {
  $('refreshBtn').addEventListener('click', () => loadParts($('searchInput').value.trim()));
  $('clearSearchBtn').addEventListener('click', () => { $('searchInput').value = ''; loadParts(''); });
  $('searchInput').addEventListener('input', () => {
    const q = $('searchInput').value.trim();
    window.clearTimeout(window.__partsTimer);
    window.__partsTimer = window.setTimeout(() => loadParts(q), 250);
  });

  $('customerSearchInput').addEventListener('input', () => {
    const q = $('customerSearchInput').value.trim();
    window.clearTimeout(customerTimer);
    customerTimer = window.setTimeout(() => searchCustomers(q), 250);
  });

  document.querySelectorAll('.mode-tab').forEach((btn) => {
    btn.addEventListener('click', () => setCustomerMode(btn.dataset.mode));
  });

  ['quickCustomerName', 'quickCustomerPhone', 'quickCustomerEmail'].forEach((id) => {
    $(id).addEventListener('input', renderSelectedCustomer);
  });

  $('paymentMethod').addEventListener('change', updatePaymentUI);
  $('cashTaxable').addEventListener('change', renderCart);
  $('checkoutBtn').addEventListener('click', checkout);
  $('productModalClose').addEventListener('click', closeProductModal);
  $('productModal').addEventListener('click', (e) => {
    if (e.target.id === 'productModal') closeProductModal();
  });
}

async function init() {
  setupEvents();
  updatePaymentUI();
  renderCart();
  renderSelectedCustomer();
  try {
    const meta = await apiGet(API.meta);
    if (meta?.zelle_email) state.zelleEmail = meta.zelle_email;
  } catch (err) {
    console.warn('Meta load failed', err);
  }
  await loadParts('');
}

document.addEventListener('DOMContentLoaded', init);
