from __future__ import annotations

from jetlinks_ai_api.openai_compat import normalize_openai_base_url, openai_base_candidates


def test_openai_base_candidates_keep_raw_tabcode_path_before_v1() -> None:
    base = "https://api.tabcode.cc/openai"
    assert openai_base_candidates(base) == [
        "https://api.tabcode.cc/openai",
        "https://api.tabcode.cc/openai/v1",
    ]


def test_normalize_openai_base_url_keeps_bigmodel_v4() -> None:
    base = "https://open.bigmodel.cn/api/paas/v4"
    assert normalize_openai_base_url(base) == base
