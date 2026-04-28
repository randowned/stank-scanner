// StankBot single-command E2E test runner (cross-platform Node.js)
// Starts the Python backend with health-check polling, runs Playwright,
// and cleans up on exit. Backend output is written to a log file.

import { spawn } from 'child_process';
import { resolve, dirname } from 'path';
import { fileURLToPath } from 'url';
import * as fs from 'fs';
import * as http from 'http';

const __dirname = dirname(fileURLToPath(import.meta.url));
const repoRoot = resolve(__dirname, '..');
const pidFile = resolve(repoRoot, '.stankbot_backend.pid');
const logFile = resolve(repoRoot, '.stankbot_backend.log');
const frontendDir = resolve(repoRoot, 'src/stankbot/web/frontend');

// ---- Helpers ----

function healthCheck() {
    return new Promise((resolve) => {
        const req = http.get('http://127.0.0.1:8000/healthz', (res) => {
            let body = '';
            res.on('data', (chunk) => (body += chunk));
            res.on('end', () => resolve(res.statusCode === 200));
        });
        req.on('error', () => resolve(false));
        req.setTimeout(2000, () => {
            req.destroy();
            resolve(false);
        });
    });
}

function killPort(port) {
    return new Promise((resolve) => {
        if (process.platform === 'win32') {
            // Use netstat + wmic which reliably kills across user sessions
            const findPid = spawn('cmd', ['/c', `netstat -ano | findstr :${port} | findstr LISTENING`], {
                stdio: 'pipe',
            });
            let output = '';
            findPid.stdout.on('data', (chunk) => (output += chunk));
            findPid.on('close', () => {
                const lines = output.trim().split(/\r?\n/);
                const pids = [];
                for (const line of lines) {
                    const parts = line.trim().split(/\s+/);
                    const pid = parseInt(parts[parts.length - 1], 10);
                    if (pid > 0) pids.push(pid);
                }
                if (pids.length > 0) {
                    console.log(`Killing stale process(es) on port ${port}: ${pids.join(', ')}`);
                    const cleanup = () => {
                        let killed = 0;
                        for (const pid of pids) {
                            const wmic = spawn('cmd', ['/c', `wmic process where processid=${pid} call terminate >nul 2>&1`], { stdio: 'ignore' });
                            wmic.on('close', () => {
                                killed++;
                                if (killed === pids.length) {
                                    setTimeout(resolve, 1000);
                                }
                            });
                        }
                    };
                    cleanup();
                } else {
                    resolve();
                }
            });
        } else {
            const findPid = spawn('sh', ['-c', `lsof -ti :${port} 2>/dev/null`], { stdio: 'pipe' });
            let output = '';
            findPid.stdout.on('data', (chunk) => (output += chunk));
            findPid.on('close', () => {
                const pids = output.trim().split(/\s+/).map(Number).filter(Boolean);
                if (pids.length > 0) {
                    console.log(`Killing stale process(es) on port ${port}: ${pids.join(', ')}`);
                }
                for (const pid of pids) {
                    try { process.kill(pid, 'SIGKILL'); } catch {}
                }
                if (pids.length > 0) {
                    setTimeout(resolve, 1000);
                } else {
                    resolve();
                }
            });
        }
    });
}

function tail(file, lines = 20) {
    try {
        const content = fs.readFileSync(file, 'utf-8');
        const all = content.split('\n').filter(Boolean);
        return all.slice(-lines).join('\n');
    } catch {
        return '(log file empty or missing)';
    }
}

// ---- Main ----

async function main() {
    // Kill stale processes
    console.log('Cleaning up stale processes...');
    await killPort(8000);
    await killPort(5173);
    await new Promise((r) => setTimeout(r, 500));

    // Start backend
    console.log('Starting backend (ENV=dev-mock)...');
    const env = { ...process.env, ENV: 'dev-mock', PYTHONPATH: resolve(repoRoot, 'src') };
    const logStream = fs.createWriteStream(logFile, { flags: 'w' });

    const backend = spawn('python', ['-m', 'stankbot'], {
        cwd: repoRoot,
        env,
        stdio: ['ignore', 'pipe', 'pipe'],
        windowsHide: true,
    });
    backend.stdout.pipe(logStream);
    backend.stderr.pipe(logStream);

    fs.writeFileSync(pidFile, String(backend.pid));
    console.log(`Backend PID: ${backend.pid}`);

    // Handle backend crash
    backend.on('exit', (code) => {
        // process already being torn down
    });

    // Wait for backend to be ready
    process.stdout.write('Waiting for backend...');
    const maxAttempts = 60; // 30s at 500ms
    let ready = false;
    for (let i = 0; i < maxAttempts; i++) {
        if (backend.exitCode !== null) {
            console.log('');
            console.error('ERROR: Backend process died during startup.');
            console.error('--- Last 20 lines of backend log ---');
            console.error(tail(logFile));
            process.exit(1);
        }
        const ok = await healthCheck();
        if (ok) {
            console.log(' ready.');
            ready = true;
            break;
        }
        await new Promise((r) => setTimeout(r, 500));
    }

    if (!ready) {
        console.log('');
        console.error(`ERROR: Backend did not become ready within 30s.`);
        console.error('--- Last 20 lines of backend log ---');
        console.error(tail(logFile));
        process.exit(1);
    }

    // Run E2E tests
    return new Promise((resolve) => {
        const tests = spawn('npm', ['run', 'test:e2e'], {
            cwd: frontendDir,
            stdio: 'inherit',
            shell: process.platform === 'win32',
        });
        tests.on('exit', (code) => {
            resolve();
            if (code !== 0) {
                process.exitCode = code ?? 1;
            }
        });
    });
}

// ---- Run ----

main()
    .catch((err) => {
        console.error('E2E runner failed:', err);
        process.exit(1);
    })
    .finally(() => {
        // Kill the backend
        try {
            const pidStr = fs.readFileSync(pidFile, 'utf-8').trim();
            const pid = parseInt(pidStr, 10);
            if (pid) {
                console.log(`Shutting down backend (PID ${pid})...`);
                if (process.platform === 'win32') {
                    spawn('cmd', ['/c', `wmic process where processid=${pid} call terminate >nul 2>&1`], { stdio: 'ignore' });
                } else {
                    try { process.kill(pid, 'SIGTERM'); } catch {}
                    setTimeout(() => {
                        try { process.kill(pid, 'SIGKILL'); } catch {}
                    }, 3000).unref();
                }
            }
        } catch {}
        try { fs.unlinkSync(pidFile); } catch {}
        console.log(`Backend log: ${logFile}`);
    });
