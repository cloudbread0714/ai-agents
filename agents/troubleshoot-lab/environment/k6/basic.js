// Plain k6 script for the k6-basics mission: prints k6's normal end-of-test summary
// (measure.js writes JSON for `lab measure` instead).
import http from 'k6/http';

export default function () {
  http.get(__ENV.TARGET_URL);
}
