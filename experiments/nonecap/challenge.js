// Return challenge metadata only, never the form's student identifiers.
const captured = (window.__nonecapPrototype || {}).widgets || [];
const visible = e => !!e && e.getClientRects().length > 0;
const candidates = captured.filter(w => {
    const node = typeof w.container === 'string' ? document.getElementById(w.container) : w.container;
    return visible(node);
});
if (candidates.length > 1) return null;
const widget = candidates[0];
const element = document.querySelector('.h-captcha[data-sitekey], [data-hcaptcha-sitekey]');
const options = widget ? widget.options : {};
let sitekey = options.sitekey || (element && (element.dataset.sitekey || element.dataset.hcaptchaSitekey));
if (!sitekey) {
    const frames = [...document.querySelectorAll('iframe[src]')].filter(e =>
        visible(e) && /(^|\.)hcaptcha\.com$/.test(new URL(e.src, location.href).hostname));
    for (const frame of frames) {
        const url = new URL(frame.src, location.href);
        const key = url.searchParams.get('sitekey') || new URLSearchParams(url.hash.slice(1)).get('sitekey');
        if (key) { if (sitekey && key !== sitekey) return null; sitekey = key; }
    }
}
if (!sitekey) return null;
return {sitekey, rqdata: options.rqdata || (element && element.dataset.rqdata) || '',
        enterprise: !!options.rqdata, user_agent: navigator.userAgent};
