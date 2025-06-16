import json
import tempfile
from scrapy.crawler import CrawlerProcess
from scrapy.utils.project import get_project_settings

from trf2.db_utils import fetch_process_numbers
from trf2.spiders.eproc_spider import EprocTrf2Spider


def main():
    processos = fetch_process_numbers()
    if not processos:
        print("Nenhum processo encontrado para processamento.")
        return

    with tempfile.NamedTemporaryFile(delete=True, suffix=".json", mode="w") as tmp:
        json.dump(processos, tmp, ensure_ascii=False)
        print(f"Lista de processos salva em {tmp.name}")

    process = CrawlerProcess(get_project_settings())
    process.crawl(EprocTrf2Spider, processos=processos)
    process.start()


if __name__ == "__main__":
    main()
