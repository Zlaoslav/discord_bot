import asyncio
import threading
import sys

class AsyncConsole:
    def __init__(self):
        self.current_process = None
        self.loop = None

    async def _ainput(self, prompt=""):
        return await asyncio.to_thread(input, prompt)

    async def _run_cmd(self, cmd: str):
        self.current_process = await asyncio.create_subprocess_exec(
            "/bin/bash", "-c", cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )

        try:
            async for line in self.current_process.stdout:
                print(line.decode(), end="")
        except asyncio.CancelledError:
            if self.current_process:
                self.current_process.kill()
            raise
        finally:
            self.current_process = None

    async def _shell(self):
        print("[CONSOLE] ready (stop / exit)")
        task = None

        while True:
            cmd = await self._ainput(">>> ")

            if cmd in ("exit", "quit"):
                if task:
                    task.cancel()
                print("[CONSOLE] exit")
                break

            if cmd == "stop":
                if self.current_process:
                    print("[CONSOLE] stopping process")
                    self.current_process.kill()
                continue

            if task and not task.done():
                print("[CONSOLE] command running, use stop")
                continue

            task = asyncio.create_task(self._run_cmd(cmd))

    def start(self):
        def runner():
            self.loop = asyncio.new_event_loop()
            asyncio.set_event_loop(self.loop)
            self.loop.run_until_complete(self._shell())

        threading.Thread(target=runner, daemon=True).start()
