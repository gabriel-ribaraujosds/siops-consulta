"""SIOPS API client — despesas por subfunção."""

import requests
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Callable, Dict, List, Optional, Tuple

import pandas as pd

BASE_URL = "https://siops-consulta-publica-api.saude.gov.br"

# Normalize estadual field names to match the municipal schema
_ESTADUAL_RENAME = {
    "descricao": "ds_item",
    "item": "co_item",
    **{f"valor{i}": f"vl_coluna{i}" for i in range(1, 11)},
}

# Normalize municipal camelCase fields
_MUNICIPAL_RENAME = {
    "dsItem": "ds_item",
    "coItem": "co_item",
}

# Internal column order (raw names before renaming)
_COL_ORDER = [
    "uf", "municipio", "ano", "periodo", "ds_item",
    *[f"vl_coluna{i}" for i in range(1, 11)],
]

# Columns to drop before returning the DataFrame
_DROP_COLS = {"quadro", "grupo", "co_item", "ordem", "id"}

# Human-readable Portuguese labels (applied after dropping unwanted columns)
COL_LABELS: Dict[str, str] = {
    "uf": "UF",
    "municipio": "Município",
    "ano": "Ano",
    "periodo": "Período",
    "ds_item": "Subfunção",
    "vl_coluna1":  "Recursos Ordinários - Fonte Livre",
    "vl_coluna2":  "Receitas de Impostos e Transferência de Impostos - Saúde",
    "vl_coluna3":  "Transf. Fundo a Fundo SUS - Governo Federal",
    "vl_coluna4":  "Transf. Fundo a Fundo SUS - Governo Estadual",
    "vl_coluna5":  "Transferências de Convênios destinadas à Saúde",
    "vl_coluna6":  "Operações de Crédito vinculadas à Saúde",
    "vl_coluna7":  "Transf. da União - LC 173/2020 art. 5º inciso I",
    "vl_coluna8":  "Royalties do Petróleo destinados à Saúde",
    "vl_coluna9":  "Outros Recursos Destinados à Saúde",
    "vl_coluna10": "TOTAL",
}


def _rename(row: dict, mapping: dict) -> dict:
    return {mapping.get(k, k): v for k, v in row.items()}


class SIOPSClient:
    def __init__(self, timeout: int = 30) -> None:
        self.session = requests.Session()
        self.session.headers.update({"Accept": "application/json"})
        self.timeout = timeout

    # ── Reference data ────────────────────────────────────────────────────────

    def get_estados(self) -> List[Dict]:
        """Returns [{co_uf, sg_uf, no_uf}, ...]."""
        r = self.session.get(f"{BASE_URL}/v1/ente/estados", timeout=self.timeout)
        r.raise_for_status()
        return r.json()

    def get_municipios(self, co_uf: str) -> List[Dict]:
        """Returns [{co_municipio, no_municipio}, ...] for the numeric UF code."""
        r = self.session.get(
            f"{BASE_URL}/v1/ente/municipal/{co_uf}", timeout=self.timeout
        )
        r.raise_for_status()
        return r.json()

    def get_anos_periodos(self) -> List[Dict]:
        """Returns [{ano, dsPeriodo, periodo}, ...] for all available year/period combos."""
        r = self.session.get(f"{BASE_URL}/v1/ente/anos", timeout=self.timeout)
        r.raise_for_status()
        return r.json()

    # ── Expenditure data ──────────────────────────────────────────────────────

    def _get_estadual(self, co_uf: str, ano: str, periodo: str) -> List[Dict]:
        """co_uf is the numeric IBGE UF code (e.g. '35' for SP)."""
        url = f"{BASE_URL}/v1/despesas-por-subfuncao/{co_uf}/{ano}/{periodo}"
        r = self.session.get(url, timeout=self.timeout)
        r.raise_for_status()
        return [_rename(row, _ESTADUAL_RENAME) for row in r.json()]

    def _get_municipal(
        self, co_uf: str, co_municipio: str, ano: str, periodo: str
    ) -> List[Dict]:
        """co_uf and co_municipio are numeric IBGE codes."""
        url = f"{BASE_URL}/v1/despesas-por-subfuncao/{co_uf}/{co_municipio}/{ano}/{periodo}"
        r = self.session.get(url, timeout=self.timeout)
        r.raise_for_status()
        return [_rename(row, _MUNICIPAL_RENAME) for row in r.json()]

    # ── Batch fetch ───────────────────────────────────────────────────────────

    def fetch_all(
        self,
        tasks: List[Tuple],
        progress_cb: Optional[Callable[[int, int], None]] = None,
        max_workers: int = 8,
    ) -> Tuple[pd.DataFrame, List[str]]:
        """
        tasks items:
          ("estadual",  co_uf, ano, periodo)
          ("municipal", co_uf, co_municipio, ano, periodo)

        Returns (DataFrame with Portuguese column labels, list_of_error_messages).
        """
        total = len(tasks)
        completed = 0
        all_rows: List[Dict] = []
        errors: List[str] = []

        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            future_map = {}
            for task in tasks:
                if task[0] == "estadual":
                    _, co_uf, ano, periodo = task
                    f = executor.submit(self._get_estadual, co_uf, ano, periodo)
                else:
                    _, co_uf, co_muni, ano, periodo = task
                    f = executor.submit(self._get_municipal, co_uf, co_muni, ano, periodo)
                future_map[f] = task

            for future in as_completed(future_map):
                task = future_map[future]
                completed += 1
                if progress_cb:
                    progress_cb(completed, total)
                try:
                    all_rows.extend(future.result())
                except Exception as exc:
                    label = "/".join(str(p) for p in task[1:])
                    errors.append(f"{task[0].upper()} {label}: {exc}")

        if not all_rows:
            return pd.DataFrame(), errors

        df = pd.DataFrame(all_rows)

        # Drop unwanted columns
        df.drop(columns=[c for c in _DROP_COLS if c in df.columns], inplace=True)

        # Reorder: known priority first, then any leftover extras
        ordered = [c for c in _COL_ORDER if c in df.columns]
        extras  = [c for c in df.columns if c not in ordered]
        df = df[ordered + extras]

        # Human-readable column labels
        df.rename(columns=COL_LABELS, inplace=True)

        return df, errors
