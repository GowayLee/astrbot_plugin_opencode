import json
import re
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
README_PATH = REPO_ROOT / "README.md"
SCHEMA_PATH = REPO_ROOT / "_conf_schema.json"
HUMAN_UAT_PATH = (
    REPO_ROOT / ".planning" / "phases" / "02.1-astrbot-phase-2" / "02.1-HUMAN-UAT.md"
)


EXPECTED_REMOVED_FIELDS = {
    "backend_type",
    "acp_client_capabilities",
    "default_agent",
    "default_mode",
    "default_config_options",
}


def load_schema_keys() -> set[str]:
    schema = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))
    return set(schema["basic_config"]["items"].keys())


def extract_readme_basic_config_fields() -> set[str]:
    readme = README_PATH.read_text(encoding="utf-8")
    match = re.search(r"## 配置项.*?### 基础配置\n\n(.*?)(?:\n> 注意：)", readme, re.S)
    assert match, "README 未找到“基础配置”表格区块"
    return set(re.findall(r"^\|\s*`([^`]+)`\s*\|", match.group(1), re.M))


def extract_readme_checklist_fields() -> set[str]:
    readme = README_PATH.read_text(encoding="utf-8")
    match = re.search(
        r"3\. 配置面板只剩以下字段：\n(.*?)(?:\n4\. 面板中不再出现)",
        readme,
        re.S,
    )
    assert match, "README 未找到真实宿主联调字段检查单"
    return set(re.findall(r"- `([^`]+)`", match.group(1)))


def extract_human_uat_fields() -> set[str]:
    content = HUMAN_UAT_PATH.read_text(encoding="utf-8")
    match = re.search(r"expected: .*?这 8 个字段，.*", content)
    assert match, "Human UAT 未找到字段期望描述"
    return set(re.findall(r"([a-z_]+)", match.group(0))) & load_schema_keys()


def test_phase_021_readme_webui_field_docs_match_schema_contract():
    schema_keys = load_schema_keys()

    assert extract_readme_basic_config_fields() == schema_keys
    assert extract_readme_checklist_fields() == schema_keys


def test_phase_021_docs_keep_manual_uat_and_removed_fields_in_sync_with_schema():
    schema_keys = load_schema_keys()
    readme = README_PATH.read_text(encoding="utf-8")

    assert extract_human_uat_fields() == schema_keys
    assert EXPECTED_REMOVED_FIELDS <= set(re.findall(r"`([^`]+)`", readme))
    assert EXPECTED_REMOVED_FIELDS.isdisjoint(schema_keys)
