// VM entry: `node serverVm.js` (see infra/lib/cms-vm.ts for the systemd unit that runs it).
import { startVmServer } from "./vmServer.js";

try {
  startVmServer();
} catch (err) {
  process.stderr.write(`${JSON.stringify({ level: "error", msg: "startup failed", meta: { message: err.message } })}\n`);
  process.exit(1);
}
