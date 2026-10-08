import math

import jwt
import pytest

from backend.app.auth.services import TokenService
from backend.shared.utils import AppError, Clock


@pytest.mark.parametrize("field", ["exp", "iat"])
@pytest.mark.parametrize("value", [math.nan, math.inf, -math.inf, True])
def test_nonfinite_or_boolean_token_dates_rejected(settings, field, value):
    service = TokenService(settings, Clock())
    payload = service.decode(service.issue("customer", 0))
    payload[field] = value
    token = jwt.encode(payload, settings.jwt_secret, algorithm="HS256")
    with pytest.raises(AppError) as exc:
        service.decode(token)
    assert exc.value.status_code == 401
