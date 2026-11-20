// Store aggregate HTTP outcomes only: no URLs, bodies, headers or tokens.
(() => {
    if (window.__submissionDiagnostic) return;
    const state = window.__submissionDiagnostic = {
        started: 0, finished: 0, network_errors: 0, aborted_requests: 0,
        request_timeouts: 0, opaque_responses: 0, unknown_status: 0,
        http_2xx: 0, http_3xx: 0, http_4xx: 0, http_5xx: 0
    };
    function end(status, outcome) {
        state.finished++;
        if (outcome === 'error') state.network_errors++;
        else if (outcome === 'abort') state.aborted_requests++;
        else if (outcome === 'timeout') state.request_timeouts++;
        else if (outcome === 'opaque') state.opaque_responses++;
        else if (!status) state.unknown_status++;
        const group = Math.floor(status / 100);
        if (group >= 2 && group <= 5) state['http_' + group + 'xx']++;
    }
    const send = XMLHttpRequest.prototype.send;
    XMLHttpRequest.prototype.send = function(...args) {
        state.started++;
        let completed = false, finalStatus = 0;
        // Some clients abort/clear an XHR inside their completion handler. Capture
        // its status first; status=0 at loadend alone does not mean network failure.
        this.addEventListener('readystatechange', () => {
            if (this.readyState === 4 && this.status) finalStatus = this.status;
        }, {capture: true});
        const finish = outcome => {
            if (completed) return;
            completed = true;
            end(finalStatus || this.status, outcome);
        };
        for (const event of ['load', 'error', 'abort', 'timeout', 'loadend']) {
            this.addEventListener(event, () => finish(event), {once: true, capture: true});
        }
        return send.apply(this, args);
    };
    const fetch = window.fetch;
    window.fetch = function(...args) {
        state.started++;
        return fetch.apply(this, args).then(
            response => { end(response.status, response.type === 'opaque' ? 'opaque' : 'load'); return response; },
            error => { end(0, error?.name === 'AbortError' ? 'abort' : 'error'); throw error; }
        );
    };
})();
