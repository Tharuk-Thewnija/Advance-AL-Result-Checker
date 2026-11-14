const token = arguments[0], responseKey = arguments[1] || '';
const fields = document.querySelectorAll('[name="h-captcha-response"], [name="g-recaptcha-response"]');
const alreadyVerified = [...fields].some(field => !!field.value);
for (const field of fields) {
    field.value = token;
    field.dispatchEvent(new Event('input', {bubbles:true}));
    field.dispatchEvent(new Event('change', {bubbles:true}));
}
const captured = (window.__nonecapPrototype || {}).widgets || [];
const visible = e => !!e && e.getClientRects().length > 0;
const widgets = captured.filter(w => visible(typeof w.container === 'string' ? document.getElementById(w.container) : w.container));
let callback = widgets.length === 1 ? widgets[0].options.callback : null;
if (!callback) callback = document.querySelector('[data-callback]')?.getAttribute('data-callback');
if (typeof callback === 'string' && /^[\w$]+(\.[\w$]+)*$/.test(callback)) {
    callback = callback.split('.').reduce((o,k) => o && Object.hasOwn(o,k) ? o[k] : null, window);
}
try {
    if (typeof callback === 'function') {
        callback(token, responseKey);
        return {applied:true, callback:true, already_verified:alreadyVerified};
    }
} catch (_) { return {applied:false}; }
return {applied:fields.length > 0, callback:false, already_verified:alreadyVerified};
