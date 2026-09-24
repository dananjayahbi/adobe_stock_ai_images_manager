"use strict";
/**
 * The shared HTTP client.
 *
 * Extracted from `api.ts` so feature-specific modules (settings, upload, …) can
 * import the configured instance without depending on the entire stage API
 * surface. Keeping one instance means the base URL and the error normalisation
 * below cannot drift between features.
 */
var __importDefault = (this && this.__importDefault) || function (mod) {
    return (mod && mod.__esModule) ? mod : { "default": mod };
};
Object.defineProperty(exports, "__esModule", { value: true });
exports.api = exports.API_BASE_URL = void 0;
const axios_1 = __importDefault(require("axios"));
exports.API_BASE_URL = process.env.NEXT_PUBLIC_API_BASE_URL || "http://localhost:8100";
exports.api = axios_1.default.create({
    baseURL: exports.API_BASE_URL,
    timeout: 60000,
});
exports.api.interceptors.response.use((response) => response, (error) => {
    // Surface the backend's `detail` string rather than axios's generic
    // "Request failed with status code 400", which hides the actual reason.
    const detail = error?.response?.data?.detail ??
        error?.message ??
        "Unexpected network error.";
    return Promise.reject(new Error(String(detail)));
});
exports.default = exports.api;
