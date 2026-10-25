// Common measurement script (contracts/measurement.md). All parameters come from env so
// baseline, fault and after measurements use exactly the same method.
import http from 'k6/http';

const method = __ENV.METHOD || 'GET';
const body = __ENV.BODY || null;
const params = { headers: { 'Content-Type': 'application/json' }, timeout: '10s' };

export const options = {
  vus: Number(__ENV.VUS || 5),
  duration: __ENV.DURATION || '20s',
  insecureSkipTLSVerify: false, // https targets trust the lab CA via SSL_CERT_FILE
  // Track latency of successful responses separately (k6 tags them expected_response:true).
  thresholds: { 'http_req_duration{expected_response:true}': ['max>=0'] },
  summaryTrendStats: ['avg', 'p(95)', 'max'],
};

export default function () {
  http.request(method, __ENV.TARGET_URL, body, params);
}

export function handleSummary(data) {
  return { '/out/summary.json': JSON.stringify(data) };
}
