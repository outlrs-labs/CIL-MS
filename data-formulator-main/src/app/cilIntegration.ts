// CIL integration: base-path routing only. Authentication remains in the FastAPI bridge.
export const cilBase = window.location.pathname.match(/^\/cmpdi\/workbench\/[0-9a-f-]{36}\//)?.[0] || '';
export const cilAnalysisId = cilBase.split('/')[3] || '';

if (cilBase) {
    document.documentElement.dataset.cilWorkbench = 'true';

    const fonts = document.createElement('link');
    fonts.rel = 'stylesheet';
    fonts.href = '/fonts/cil-fonts.css';
    document.head.appendChild(fonts);

    const originalFetch = window.fetch.bind(window);
    window.fetch = (input, init) => {
        const raw = input instanceof Request ? input.url : input.toString();
        const parsed = new URL(raw, window.location.origin);
        if (parsed.origin === window.location.origin && parsed.pathname.startsWith('/api/')) {
            const next = cilBase + parsed.pathname.slice(1) + parsed.search;
            return originalFetch(input instanceof Request ? new Request(next, input) : next, init);
        }
        return originalFetch(input, init);
    };
}
