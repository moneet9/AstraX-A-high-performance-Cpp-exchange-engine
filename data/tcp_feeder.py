"""Binary TCP market-data feeder for AstraX.

Streams replay orders over a fixed-width binary protocol so the dashboard
server can decode and submit them without text serialization overhead.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from typing import Iterable, Optional

import exchange_simulator as ex


@dataclass
class TcpFeederConfig:
    host: str = "127.0.0.1"
    port: int = 8766
    send_delay_ns: int = 0


class TcpMarketDataFeeder:
    def __init__(self, config: Optional[TcpFeederConfig] = None):
        self.config = config or TcpFeederConfig()

    async def feed_orders(self, orders: Iterable[ex.Order]) -> None:
        _, writer = await asyncio.open_connection(self.config.host, self.config.port)
        try:
            for order in orders:
                frame = ex.BinaryProtocol.encode_order(order)
                writer.write(frame)
                await writer.drain()

                if self.config.send_delay_ns > 0:
                    await asyncio.sleep(self.config.send_delay_ns / 1_000_000_000)
        finally:
            writer.close()
            await writer.wait_closed()

    async def feed_replay(self, replay_source) -> None:
        _, writer = await asyncio.open_connection(self.config.host, self.config.port)
        try:
            for event in replay_source:
                if hasattr(event, "to_order"):
                    order = event.to_order()
                else:
                    order = event

                if order is not None:
                    frame = ex.BinaryProtocol.encode_order(order)
                    writer.write(frame)
                    await writer.drain()

                    if self.config.send_delay_ns > 0:
                        await asyncio.sleep(self.config.send_delay_ns / 1_000_000_000)
        finally:
            writer.close()
            await writer.wait_closed()


async def main():
    import argparse

    parser = argparse.ArgumentParser(description="AstraX binary TCP market-data feeder")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8766)
    parser.add_argument("--source", required=True, help="Path to a replay CSV file")
    args = parser.parse_args()

    from data.replay import LobsterReplay

    feeder = TcpMarketDataFeeder(TcpFeederConfig(host=args.host, port=args.port))
    replay = LobsterReplay(args.source)
    await feeder.feed_replay(replay.generate())


if __name__ == "__main__":
    asyncio.run(main())

# AstraX repo sync
