"""Durable Redis Stream consumer that delivers simulated-fill APNs alerts."""
import asyncio
import os
from pathlib import Path

from redis import asyncio as aioredis

STREAM = "astrax:push:events"
GROUP = "apns-workers"


async def main():
    required = ("APNS_KEY_ID", "APNS_TEAM_ID", "APNS_BUNDLE_ID", "APNS_PRIVATE_KEY_PATH")
    missing = [name for name in required if not os.getenv(name)]
    if missing:
        raise RuntimeError("Missing APNs settings: " + ", ".join(missing))
    from aioapns import APNs, NotificationRequest

    redis = aioredis.from_url(os.getenv("REDIS_URL", "redis://localhost:6379/0"), decode_responses=True)
    try:
        await redis.xgroup_create(STREAM, GROUP, id="0", mkstream=True)
    except Exception as exc:
        if "BUSYGROUP" not in str(exc):
            raise
    provider = APNs(key=Path(os.environ["APNS_PRIVATE_KEY_PATH"]).read_text(),
                    key_id=os.environ["APNS_KEY_ID"], team_id=os.environ["APNS_TEAM_ID"],
                    bundle_id=os.environ["APNS_BUNDLE_ID"],
                    use_sandbox=os.getenv("APNS_SANDBOX", "true").lower() == "true")
    consumer = os.getenv("ASTRAX_APNS_CONSUMER", "apns-worker")
    try:
        while True:
            # Reclaim this stable worker's own pending deliveries after restart
            # before reading new stream entries.
            batches = await redis.xreadgroup(GROUP, consumer, {STREAM: "0"}, count=20)
            if not batches:
                batches = await redis.xreadgroup(GROUP, consumer, {STREAM: ">"}, count=20, block=5000)
            for _, records in batches:
                for record_id, fields in records:
                    request = NotificationRequest(device_token=fields["token"], message={"aps": {"alert": {
                        "title": fields["title"], "body": fields["body"]}}})
                    delivered = False
                    for attempt in range(3):
                        try:
                            await provider.send_notification(request)
                            delivered = True
                            break
                        except Exception:
                            await asyncio.sleep(2 ** attempt)
                    # Ack after successful delivery or bounded retries so a bad
                    # token cannot block the stream. APNs tokens can be removed
                    # by the account owner when the app unregisters.
                    if delivered or fields.get("token"):
                        await redis.xack(STREAM, GROUP, record_id)
    finally:
        await redis.aclose()


if __name__ == "__main__":
    asyncio.run(main())
