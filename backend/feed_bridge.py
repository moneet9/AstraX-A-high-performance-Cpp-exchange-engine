"""TCP adapter for the engine's fixed-width binary order and fill frames."""
import asyncio
import os


ORDER_FRAME_SIZE = 54


async def serve_tcp_feed(engine, lock, on_change, host: str | None = None, port: int | None = None):
    async def client(reader: asyncio.StreamReader, writer: asyncio.StreamWriter):
        try:
            while True:
                frame = await reader.readexactly(ORDER_FRAME_SIZE)
                import exchange_simulator as ex
                order = ex.BinaryProtocol.decode_order(frame)
                if order is None:
                    continue
                with lock:
                    fills = engine.submit(order)
                for fill in fills:
                    writer.write(ex.BinaryProtocol.encode_fill(fill))
                if fills:
                    await writer.drain()
                await on_change(fills)
        except (asyncio.IncompleteReadError, ConnectionError):
            pass
        finally:
            writer.close()
            await writer.wait_closed()

    return await asyncio.start_server(client, host or os.getenv("ASTRAX_FEED_HOST", "127.0.0.1"),
                                      port or int(os.getenv("ASTRAX_FEED_PORT", "8771")))
