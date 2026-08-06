import asyncio, json, re
from playwright.async_api import async_playwright

async def check():
    with open('data/us/member_careers.json') as f:
        careers = json.load(f)
    na_ids = [k for k,v in careers.items() if v.get('career') == 'NA']
    print(f'Total NA: {len(na_ids)}')

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        page = await browser.new_page(
            user_agent='Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36'
        )
        await page.goto('https://bioguide.congress.gov', wait_until='networkidle', timeout=30000)
        await page.wait_for_timeout(3000)

        for bid in na_ids[:20]:
            try:
                await page.goto(
                    f'https://bioguide.congress.gov/search/bio/{bid}',
                    wait_until='networkidle', timeout=30000
                )
                await page.wait_for_timeout(2000)
                text = await page.inner_text('body')
                bio = re.search(r'born in .{0,400}', text, re.DOTALL)
                if bio:
                    print(f'{bid}: {bio.group()[:250]}')
                else:
                    print(f'{bid}: NO BIO FOUND')
                print()
            except Exception as e:
                print(f'{bid}: ERROR {e}')

        await browser.close()

asyncio.run(check())
