"""
Twilio SMS provider implementation.
"""


import structlog

from src.config.settings import get_settings
from src.core.exceptions import ProviderError
from src.providers.base import BaseSMSProvider, ProviderResponse, SMSMessage

logger = structlog.get_logger(__name__)
settings = get_settings()


class TwilioSMSProvider(BaseSMSProvider):
    """SMS provider using Twilio API."""

    def __init__(self) -> None:
        self._account_sid = settings.twilio.account_sid.get_secret_value()
        self._auth_token = settings.twilio.auth_token.get_secret_value()
        self._from_number = settings.twilio.phone_number
        self._timeout = settings.twilio.timeout
        self._client = None

    def _get_client(self):
        """Lazy-load Twilio client."""
        if self._client is None:
            try:
                from twilio.rest import Client

                self._client = Client(self._account_sid, self._auth_token)
            except ImportError as e:
                raise ProviderError(
                    "Twilio package not installed. Install with: pip install twilio",
                    provider="twilio",
                ) from e
        return self._client

    async def send(self, message: SMSMessage) -> ProviderResponse:
        """Send a single SMS via Twilio."""
        try:
            client = self._get_client()
            from_number = message.from_number or self._from_number

            if not from_number:
                return ProviderResponse(
                    success=False,
                    error_message="No sender phone number configured",
                    provider_code="CONFIG_ERROR",
                    retryable=False,
                    metadata={"provider": "twilio"},
                )

            results = []
            for to_number in message.to:
                # Twilio client is synchronous, run in executor
                import asyncio

                result = await asyncio.to_thread(
                    client.messages.create,
                    body=message.content,
                    from_=from_number,
                    to=to_number,
                )
                results.append({
                    "to": to_number,
                    "sid": result.sid,
                    "status": result.status,
                    "price": str(result.price) if result.price else None,
                })

            logger.info(
                "sms_sent_via_twilio",
                to=message.to,
                results_count=len(results),
            )

            return ProviderResponse(
                success=True,
                provider_message_id=results[0]["sid"] if results else None,
                raw_response={"results": results},
                metadata={
                    "provider": "twilio",
                    "recipients": len(results),
                    "total_cost": sum(
                        float(r["price"] or 0) for r in results
                    ),
                },
            )

        except Exception as e:
            error_str = str(e)
            # Twilio error codes
            provider_code = "TWILIO_ERROR"
            retryable = True

            if "21211" in error_str:  # Invalid phone number
                provider_code = "INVALID_NUMBER"
                retryable = False
            elif "21217" in error_str:  # Queue overflow
                provider_code = "QUEUE_OVERFLOW"
                retryable = True
            elif "21610" in error_str:  # Cannot send to unsubscribed
                provider_code = "UNSUBSCRIBED"
                retryable = False

            logger.error(
                "sms_send_failed",
                to=message.to,
                error=error_str,
                provider_code=provider_code,
            )

            return ProviderResponse(
                success=False,
                error_message=error_str,
                provider_code=provider_code,
                retryable=retryable,
                metadata={"provider": "twilio"},
            )

    async def send_bulk(self, messages: list[SMSMessage]) -> list[ProviderResponse]:
        """Send multiple SMS messages with rate limiting."""
        import asyncio

        semaphore = asyncio.Semaphore(5)  # Twilio rate limit protection

        async def send_with_limit(msg: SMSMessage) -> ProviderResponse:
            async with semaphore:
                result = await self.send(msg)
                # Add small delay between sends
                await asyncio.sleep(0.1)
                return result

        tasks = [send_with_limit(msg) for msg in messages]
        return await asyncio.gather(*tasks, return_exceptions=False)

    async def health_check(self) -> bool:
        """Check Twilio API connectivity."""
        try:
            client = self._get_client()
            import asyncio

            await asyncio.to_thread(client.api.accounts(self._account_sid).fetch)
            return True
        except Exception:
            return False
