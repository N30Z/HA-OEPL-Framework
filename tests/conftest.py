import aiohttp.connector
import aiohttp.resolver
import pytest

pytest_plugins = "pytest_homeassistant_custom_component"

# aiodns/pycares is a transitive `homeassistant` dependency. When installed,
# it becomes aiohttp's DefaultResolver, and constructing it (as
# pytest-homeassistant-custom-component's aioclient_mock does for every
# mocked ClientSession) eagerly spawns a background "_run_safe_shutdown_loop"
# thread that lingers past the per-test thread-leak check. Tests never need
# real DNS resolution since all HTTP calls go through aioclient_mock, so use
# the plain threaded resolver instead. aiohttp.connector imports
# DefaultResolver by name at module load time, so both bindings must be
# patched.
aiohttp.resolver.DefaultResolver = aiohttp.resolver.ThreadedResolver
aiohttp.connector.DefaultResolver = aiohttp.resolver.ThreadedResolver


@pytest.fixture(autouse=True)
def auto_enable_custom_integrations(enable_custom_integrations):
    yield
