// Return classifications only. Never return page text, input values or URLs.
const visible = e => !!(e.getClientRects().length && getComputedStyle(e).visibility !== 'hidden');
const cards = [...document.querySelectorAll('.card.border-info.watermark')];
const messages = [...document.querySelectorAll('.toast-message,[role="alertdialog"],[role="alert"],.alert,.ui-messages,.ui-message,.invalid-feedback,.error')]
    .filter(visible).map(e => e.textContent.toLowerCase()).join(' ');
const network = window.__submissionDiagnostic || {};
return {
    result_visible: cards.some(e => visible(e) && e.textContent.trim().length > 0),
    captcha_message: /captcha|verification|robot/.test(messages),
    no_result_message: /no results?|not found|invalid nic|invalid index/.test(messages),
    busy_message: /try again|busy|too many|temporar|unavailable/.test(messages),
    alert_visible: !!messages.trim(),
    site_notice_latched: window.__alSiteNoticeSeen === true,
    site_notice_visible: messages.replace(/\s+/g,' ').includes('sorry for the inconvenience, please try again'),
    response_present: [...document.querySelectorAll('[name="h-captcha-response"],[name="g-recaptcha-response"]')].some(e => !!e.value),
    pending_requests: Math.max(0, (network.started || 0) - (network.finished || 0)),
    network_errors: network.network_errors || 0,
    aborted_requests: network.aborted_requests || 0,
    request_timeouts: network.request_timeouts || 0,
    opaque_responses: network.opaque_responses || 0,
    unknown_status: network.unknown_status || 0,
    http_2xx: network.http_2xx || 0, http_3xx: network.http_3xx || 0,
    http_4xx: network.http_4xx || 0, http_5xx: network.http_5xx || 0
};
