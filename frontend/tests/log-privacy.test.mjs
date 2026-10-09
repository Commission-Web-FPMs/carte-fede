import test from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
for (const file of ['nginx/default.conf.template', '../nginx/nginx.conf']) {
  test(`${file} omits request targets, client addresses and headers`, () => {
    const config = readFileSync(new URL(`../${file}`, import.meta.url), 'utf8');
    assert.match(config, /log_format privacy '\$privacy_method \$status \$request_time';/);
    assert.match(config, /default OTHER;/);
    assert.match(config, /access_log \/dev\/stdout privacy;/);
    assert.match(config, /error_log \/dev\/null;/);
    if (file.endsWith('template')) assert.match(config, /server \{[\s\S]*?access_log \/dev\/stdout privacy;[\s\S]*?error_log \/dev\/null;/);
    const format = config.match(/log_format privacy ([^;]+);/)[1];
    for (const field of ['$request_uri', '$request', '$args', '$http_cookie', '$http_authorization', '$remote_addr']) assert.ok(!(format.match(/\$[a-z_]+/g) || []).includes(field));
  });
}
