import { randomUUID } from 'node:crypto';
import { existsSync } from 'node:fs';
import { spawn, spawnSync } from 'node:child_process';
import { fileURLToPath } from 'node:url';

const root = fileURLToPath(new URL('../', import.meta.url));
const localPython = fileURLToPath(new URL(process.platform === 'win32' ? '../.venv/Scripts/python.exe' : '../.venv/bin/python', import.meta.url));
const python = process.env.SONDA_PYTHON || (existsSync(localPython) ? localPython : 'python');
const schema = 'st_' + randomUUID().replaceAll('-', '');
const child = spawn(python, ['-m', 'tests.e2e_server', '--schema', schema, '--port', '5117'], { cwd: root, stdio: 'inherit', windowsHide: true });
for (const signal of ['SIGINT', 'SIGTERM']) process.on(signal, () => child.kill(signal));
child.on('exit', code => {
  const cleanup = spawnSync(python, ['-m', 'tests.e2e_server', '--schema', schema, '--port', '5117', '--cleanup'], { cwd: root, stdio: 'inherit', windowsHide: true });
  process.exit(code ?? cleanup.status ?? 0);
});
