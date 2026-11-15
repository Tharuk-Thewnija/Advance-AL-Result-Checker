// Submit only an unambiguous, visible, enabled action.
const visible = e => e.getClientRects().length > 0 && !e.disabled;
const buttons = [...document.querySelectorAll('button, input[type="submit"]')].filter(visible);
let matches = buttons.filter(e => /^(submit|view results?|search|get results?)$/i.test((e.innerText || e.value || '').trim()));
if (!matches.length) matches = buttons.filter(e => e.type === 'submit');
if (matches.length !== 1) return false;
matches[0].click();
return true;
