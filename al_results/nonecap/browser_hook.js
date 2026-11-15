// Runs before page scripts. Capture the site's own render callback without
// changing challenge behaviour in manual mode (which never installs this hook).
(() => {
    const state = window.__nonecapPrototype = { widgets: [] };
    function wrap(api) {
        if (!api || typeof api.render !== 'function' || api.render.__nonecapWrapped) return api;
        const original = api.render;
        function render(container, options = {}) {
            const entry = { container, options, id: null };
            entry.id = original.call(this, container, options);
            state.widgets.push(entry);
            return entry.id;
        }
        render.__nonecapWrapped = true;
        api.render = render;
        return api;
    }
    let value = window.hcaptcha;
    try {
        Object.defineProperty(window, 'hcaptcha', {
            configurable: true, enumerable: true,
            get() { return value; }, set(api) { value = wrap(api); }
        });
        wrap(value);
    } catch (_) { /* The adapter will fall back to manual if capture fails. */ }
})();
