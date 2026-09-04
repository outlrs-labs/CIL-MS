import '@testing-library/jest-dom/vitest';
import {vi} from 'vitest';
// jsdom has no viewport scrolling; the browser checks exercise real scrolling.
if(typeof window!=='undefined')window.scrollTo=vi.fn();
