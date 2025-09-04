import asyncio
from playwright.async_api import async_playwright

PROPERTY_URL = "https://jennacooperla.com/pages/7904-woodrow-wilson-dr"  # Example property with gallery

async def test_gallery_images():
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        page = await browser.new_page()
        await page.goto(PROPERTY_URL)
        # Wait for gallery to load (optional: adjust selector or timeout as needed)
        await page.wait_for_selector(".xo-gallery .swiper-slide img", timeout=10000)
        img_urls = await page.eval_on_selector_all(
            ".xo-gallery .swiper-slide img",
            "nodes => nodes.map(n => n.src)"
        )
        print(f"Found {len(img_urls)} gallery images:")
        for url in img_urls:
            print(url)
        await browser.close()

if __name__ == "__main__":
    asyncio.run(test_gallery_images()) 