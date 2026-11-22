import os
import tempfile

# Isolated database and no background tasks for every test run (must be set before app imports)
os.environ["DATA_DIR"] = tempfile.mkdtemp(prefix="exunu-test-")
os.environ.pop("DATABASE_URL", None)
os.environ["SCHEDULER_ENABLED"] = "false"
os.environ["TELEGRAM_POLLING"] = "false"
os.environ["ADMIN_USERNAME"] = "admin"
os.environ["ADMIN_ACCESS_CODE"] = "admin-test-code"
os.environ["TELEGRAM_BOT_TOKEN"] = ""
os.environ["GEMINI_API_KEY"] = ""
