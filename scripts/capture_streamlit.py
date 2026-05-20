from pathlib import Path
import time

from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.action_chains import ActionChains
from selenium.webdriver.common.by import By
from selenium.common.exceptions import TimeoutException
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait


ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "docs" / "capturas"
URL = "http://localhost:8501"


def wait_ready(driver: webdriver.Chrome) -> None:
    WebDriverWait(driver, 30).until(EC.presence_of_element_located((By.TAG_NAME, "h1")))
    time.sleep(2)


def click_text(driver: webdriver.Chrome, text: str) -> None:
    xpath = f"//*[normalize-space()='{text}']"
    element = WebDriverWait(driver, 20).until(EC.element_to_be_clickable((By.XPATH, xpath)))
    driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", element)
    time.sleep(0.3)
    driver.execute_script("arguments[0].click();", element)
    time.sleep(1.2)


def click_label(driver: webdriver.Chrome, text: str) -> None:
    label = WebDriverWait(driver, 20).until(
        EC.presence_of_element_located((By.XPATH, f"//label[contains(normalize-space(), '{text}')]"))
    )
    driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", label)
    time.sleep(0.3)
    driver.execute_script("arguments[0].click();", label)
    time.sleep(1.2)


def click_button(driver: webdriver.Chrome, text: str) -> None:
    button = WebDriverWait(driver, 20).until(
        EC.element_to_be_clickable((By.XPATH, f"//button[contains(normalize-space(), '{text}')]"))
    )
    driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", button)
    time.sleep(0.3)
    driver.execute_script("arguments[0].click();", button)
    time.sleep(1.2)


def screenshot(driver: webdriver.Chrome, name: str, y: int = 0) -> None:
    driver.execute_script(
        """
        const y = arguments[0];
        window.scrollTo(0, y);
        document.documentElement.scrollTop = y;
        document.body.scrollTop = y;
        const containers = [
          document.querySelector('section[data-testid="stMain"]'),
          document.querySelector('[data-testid="stAppViewContainer"]'),
          document.querySelector('section.main'),
          document.querySelector('.main')
        ].filter(Boolean);
        for (const el of containers) { el.scrollTop = y; }
        """,
        y,
    )
    if y:
        ActionChains(driver).scroll_by_amount(0, y).perform()
    time.sleep(1.2)
    driver.save_screenshot(str(OUT / name))


def screenshot_near_text(driver: webdriver.Chrome, text: str, name: str) -> None:
    element = WebDriverWait(driver, 20).until(
        EC.presence_of_element_located((By.XPATH, f"//*[normalize-space()='{text}']"))
    )
    driver.execute_script(
        """
        const el = arguments[0];
        const container = document.querySelector('section[data-testid="stMain"]');
        if (container) {
          const elTop = el.getBoundingClientRect().top;
          const containerTop = container.getBoundingClientRect().top;
          container.scrollTop = Math.max(0, container.scrollTop + elTop - containerTop - 80);
        } else {
          el.scrollIntoView({block: 'start'});
        }
        """,
        element,
    )
    time.sleep(1.2)
    driver.save_screenshot(str(OUT / name))


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    options = Options()
    options.add_argument("--headless=new")
    options.add_argument("--window-size=1600,1100")
    options.add_argument("--disable-gpu")
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    driver = webdriver.Chrome(options=options)
    try:
        driver.get(URL)
        wait_ready(driver)
        screenshot(driver, "figura_00_selector_estacion_aemet.png", 0)
        screenshot(driver, "figura_01_formulario_configuracion.png", 260)

        click_button(driver, "Calcular recomendación de riego")
        try:
            WebDriverWait(driver, 30).until(
                EC.presence_of_element_located((By.XPATH, "//*[contains(normalize-space(), 'Riego total')]"))
            )
        except TimeoutException as exc:
            driver.save_screenshot(str(OUT / "debug_error_streamlit.png"))
            body = driver.find_element(By.TAG_NAME, "body").text
            raise RuntimeError(body[:2000]) from exc
        time.sleep(2)
        screenshot(driver, "figura_03_resultados_principales.png", 600)
        screenshot_near_text(driver, "Predicción ML", "figura_04_prediccion_ml.png")
        screenshot_near_text(driver, "Descargar informe Markdown", "figura_05_descarga_informes.png")
    finally:
        driver.quit()


if __name__ == "__main__":
    main()
