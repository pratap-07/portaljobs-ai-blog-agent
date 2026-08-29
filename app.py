import os
import json
import re
import base64
import requests
import streamlit as st

from bs4 import BeautifulSoup
from openai import OpenAI
from dotenv import load_dotenv

load_dotenv()

WORDPRESS_URL = os.getenv("WORDPRESS_URL")
WORDPRESS_USERNAME = os.getenv("WORDPRESS_USERNAME")
WORDPRESS_APP_PASSWORD = os.getenv("WORDPRESS_APP_PASSWORD")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")

if WORDPRESS_APP_PASSWORD:
    WORDPRESS_APP_PASSWORD = WORDPRESS_APP_PASSWORD.replace(" ", "")

BASE_URL = WORDPRESS_URL.rstrip("/")
API_BASE = f"{BASE_URL}/wp-json/wp/v2"

AUTH = (
    WORDPRESS_USERNAME,
    WORDPRESS_APP_PASSWORD
)

client = OpenAI(
    api_key=OPENAI_API_KEY
)

ALLOWED_CATEGORIES = [
    "Exam Syllabus",
    "Fresher Jobs",
    "Government Job",
    "सरकारी योजना"
]

BLOCKED_CATEGORIES = [
    "Uncategorized",
    "uncategorized"
]


def extract_article(url):

    headers = {
        "User-Agent": "Mozilla/5.0"
    }

    response = requests.get(
        url,
        headers=headers,
        timeout=30
    )

    response.raise_for_status()

    soup = BeautifulSoup(
        response.text,
        "html.parser"
    )

    for element in soup([
        "script",
        "style",
        "nav",
        "footer",
        "header",
        "aside",
        "form"
    ]):
        element.decompose()

    title = ""

    if soup.title:
        title = soup.title.get_text(
            " ",
            strip=True
        )

    paragraphs = soup.find_all("p")

    content = "\n".join(
        p.get_text(
            " ",
            strip=True
        )
        for p in paragraphs
        if len(
            p.get_text(strip=True)
        ) > 40
    )

    return title, content


def extract_important_information(
    source_title,
    source_content
):

    prompt = f"""
आप Hindi recruitment/blog information extraction specialist हैं।

नीचे दिए गए source article से केवल वही महत्वपूर्ण जानकारी निकालें
जो वास्तव में source में मौजूद है।

कोई जानकारी invent या अनुमान न करें।

JSON में output दें:

{{
  "rows": [
    {{
      "label": "",
      "value": ""
    }}
  ]
}}

Rules:

1. Maximum 15 rows.
2. सबसे महत्वपूर्ण जानकारी पहले रखें।
3. Government job के लिए उपलब्ध होने पर:
   भर्ती का नाम, पद, कुल पद, योग्यता, आयु सीमा,
   वेतन, आवेदन शुल्क, आवेदन शुरू, अंतिम तिथि,
   चयन प्रक्रिया, आवेदन माध्यम जैसी जानकारी निकालें।
4. Exam article के लिए उपलब्ध होने पर:
   परीक्षा नाम, कुल प्रश्न, कुल अंक, समय,
   negative marking, विषय आदि निकालें।
5. जो जानकारी source में नहीं है उसे मत बनाएं।
6. Empty या duplicate rows न दें।
7. Hindi में concise values दें।

Source Title:
{source_title}

Source Content:
{source_content}
"""

    response = client.responses.create(
        model="gpt-5",
        input=prompt
    )

    result = response.output_text.strip()

    if result.startswith("```"):
        result = result.replace("```json", "")
        result = result.replace("```", "")
        result = result.strip()

    data = json.loads(result)

    return data.get("rows", [])


def generate_blog(
    source_title,
    source_content,
    information_rows,
    word_count
):

    prompt = f"""
आप एक professional Hindi blogger और SEO writer हैं।

Source article के आधार पर एक नई और original Hindi blog post लिखें।

IMPORTANT RULES:

1. Source को word-to-word copy न करें।
2. केवल translation न करें।
3. Facts invent न करें।
4. Natural Hindi लिखें।
5. लगभग {word_count} शब्द लिखें।
6. Clear H2/H3 headings रखें।
7. Introduction के तुरंत बाद
   "महत्वपूर्ण जानकारी" section रखें।
8. Important Information table की जानकारी
   article के content के साथ consistent रखें।
9. Conclusion दें।
10. 3-5 FAQs दें।
11. यदि source में कोई जानकारी उपलब्ध नहीं है,
    तो उसे अनुमान से न लिखें।

IMPORTANT INFORMATION:

{json.dumps(
    information_rows,
    ensure_ascii=False
)}

OUTPUT:

# SEO Title

## Introduction

## महत्वपूर्ण जानकारी

[यहाँ table placeholder रखें]

## मुख्य जानकारी

## महत्वपूर्ण बातें

## Conclusion

## Frequently Asked Questions (FAQ)

Source Title:
{source_title}

Source Content:
{source_content}
"""

    response = client.responses.create(
        model="gpt-5",
        input=prompt
    )

    return response.output_text


def generate_seo(blog):

    prompt = f"""
आप expert Hindi SEO specialist हैं।

केवल valid JSON दें:

{{
  "seo_title": "",
  "meta_description": "",
  "focus_keyword": "",
  "related_keywords": [],
  "slug": "",
  "category": "",
  "tags": []
}}

Rules:

SEO title लगभग 50-60 characters.

Meta description लगभग 140-160 characters.

Focus keyword realistic search phrase हो।

5-10 related keywords दें।

Short English/Roman Hindi slug दें।

Category केवल:

Exam Syllabus
Fresher Jobs
Government Job
सरकारी योजना

Uncategorized कभी select न करें।

5-10 relevant tags दें।

Facts invent न करें।

BLOG:

{blog}
"""

    response = client.responses.create(
        model="gpt-5",
        input=prompt
    )

    result = response.output_text.strip()

    if result.startswith("```"):
        result = result.replace("```json", "")
        result = result.replace("```", "")
        result = result.strip()

    return json.loads(result)
# =========================================================
# WORDPRESS CATEGORIES
# =========================================================

def get_categories():

    response = requests.get(
        f"{API_BASE}/categories",
        params={
            "per_page": 100
        },
        auth=AUTH,
        timeout=30
    )

    response.raise_for_status()

    return response.json()


def get_category_id(
    ai_category,
    categories
):

    ai_category = ai_category.strip()

    if ai_category.lower() in [
        x.lower()
        for x in BLOCKED_CATEGORIES
    ]:
        ai_category = "Government Job"

    selected_category = None

    for allowed in ALLOWED_CATEGORIES:

        if allowed.lower() == ai_category.lower():

            selected_category = allowed
            break

    if not selected_category:

        selected_category = "Government Job"

    for category in categories:

        name = category.get(
            "name",
            ""
        )

        if name.lower() == selected_category.lower():

            if name.lower() in [
                x.lower()
                for x in BLOCKED_CATEGORIES
            ]:
                continue

            return (
                category["id"],
                name
            )

    return (
        None,
        None
    )


# =========================================================
# WORDPRESS TAGS
# =========================================================

def get_or_create_tag(tag_name):

    tag_name = tag_name.strip()

    if not tag_name:
        return None

    response = requests.get(
        f"{API_BASE}/tags",
        params={
            "search": tag_name,
            "per_page": 100
        },
        auth=AUTH,
        timeout=30
    )

    response.raise_for_status()

    existing_tags = response.json()

    for tag in existing_tags:

        if (
            tag.get("name", "").lower()
            == tag_name.lower()
        ):

            return tag["id"]

    response = requests.post(
        f"{API_BASE}/tags",
        json={
            "name": tag_name
        },
        auth=AUTH,
        timeout=30
    )

    if response.status_code == 201:

        return response.json()["id"]

    return None


# =========================================================
# GET EXISTING WORDPRESS POSTS
# =========================================================

def get_existing_posts():

    posts = []

    page = 1

    while page <= 5:

        response = requests.get(
            f"{API_BASE}/posts",
            params={
                "per_page": 100,
                "page": page,
                "_fields": "id,link,title,slug,excerpt"
            },
            auth=AUTH,
            timeout=30
        )

        if response.status_code == 400:
            break

        response.raise_for_status()

        page_posts = response.json()

        if not page_posts:
            break

        posts.extend(page_posts)

        total_pages = int(
            response.headers.get(
                "X-WP-TotalPages",
                page
            )
        )

        if page >= total_pages:
            break

        page += 1

    return posts
# =========================================================
# INTERNAL LINKS
# =========================================================

def find_internal_links(blog, posts):

    if not posts:
        return []

    post_data = []

    for post in posts:

        title = (
            post.get("title", {})
            .get("rendered", "")
        )

        link = post.get("link", "")

        if title and link:

            post_data.append({
                "title": title,
                "url": link
            })

    post_data = post_data[:300]

    prompt = f"""
आप Hindi SEO internal linking specialist हैं।

नए blog के लिए केवल genuinely relevant internal links चुनें।

Rules:
1. Maximum 3 links.
2. केवल highly relevant posts चुनें।
3. Unrelated posts को select न करें।
4. एक post को दो बार select न करें।
5. Relevant post न मिले तो empty list दें।

Output केवल valid JSON:

{{
  "links": [
    {{
      "title": "",
      "url": "",
      "anchor_text": ""
    }}
  ]
}}

NEW BLOG:
{blog}

EXISTING POSTS:
{json.dumps(post_data, ensure_ascii=False)}
"""

    response = client.responses.create(
        model="gpt-5",
        input=prompt
    )

    result = response.output_text.strip()

    if result.startswith("```"):
        result = result.replace("```json", "")
        result = result.replace("```", "")
        result = result.strip()

    try:

        data = json.loads(result)

        return data.get("links", [])

    except Exception:

        return []
# =========================================================
# EXTRACT EXTERNAL LINKS FROM SOURCE
# =========================================================

def extract_external_links(url):

    headers = {
        "User-Agent": "Mozilla/5.0"
    }

    try:

        response = requests.get(
            url,
            headers=headers,
            timeout=30
        )

        response.raise_for_status()

        soup = BeautifulSoup(
            response.text,
            "html.parser"
        )

        links = []

        for a in soup.find_all("a"):

            href = a.get("href")

            text = a.get_text(
                " ",
                strip=True
            )

            if not href:
                continue

            if not href.startswith("http"):
                continue

            # Apni website ke links ko external link nahi maana jayega
            if "portaljobs.in" in href.lower():
                continue

            if not text:
                continue

            links.append({
                "text": text[:150],
                "url": href
            })


        # Duplicate URLs remove
        unique_links = []

        seen = set()

        for item in links:

            url_value = item["url"]

            if url_value not in seen:

                seen.add(
                    url_value
                )

                unique_links.append(
                    item
                )


        return unique_links[:50]


    except Exception as e:

        print(
            f"External links extract error: {e}"
        )

        return []

# =========================================================
# EXTERNAL LINKS
# =========================================================

def select_external_links(blog, links):

    if not links:
        return []

    prompt = f"""
आप Hindi SEO और fact-checking specialist हैं।

नीचे source article के external links दिए गए हैं।

इनमें से केवल authoritative और relevant links चुनें।

Priority:
1. Official government website
2. Official application portal
3. Official notification
4. Official department website
5. Highly authoritative source

Rules:
1. Maximum 3 links.
2. Random/low-quality website को select न करें।
3. केवल genuinely useful links चुनें।
4. Relevant link न मिले तो empty list दें।

Output केवल JSON:

{{
  "links": [
    {{
      "url": "",
      "anchor_text": ""
    }}
  ]
}}

BLOG:
{blog}

AVAILABLE LINKS:
{json.dumps(links, ensure_ascii=False)}
"""

    response = client.responses.create(
        model="gpt-5",
        input=prompt
    )

    result = response.output_text.strip()

    if result.startswith("```"):
        result = result.replace("```json", "")
        result = result.replace("```", "")
        result = result.strip()

    try:

        data = json.loads(result)

        return data.get("links", [])

    except Exception:

        return []


# =========================================================
# ADD LINKS TO BLOG
# =========================================================

def add_links_to_blog(
    blog,
    internal_links,
    external_links
):

    if not internal_links and not external_links:
        return blog

    prompt = f"""
आप एक professional Hindi SEO editor हैं।

नीचे blog और relevant links दिए गए हैं।

Article में links को naturally integrate करें।

Rules:

1. Internal links maximum 3.
2. External links maximum 3.
3. Link केवल relevant sentence में लगाएं।
4. Unrelated links न लगाएं।
5. Keyword stuffing न करें।
6. Anchor text natural रखें।
7. HTML <a href="URL">anchor text</a> format use करें।
8. Article की factual information को न बदलें।
9. Existing headings को न बिगाड़ें।
10. केवल जरूरत वाली जगह links add करें।

INTERNAL LINKS:
{json.dumps(internal_links, ensure_ascii=False)}

EXTERNAL LINKS:
{json.dumps(external_links, ensure_ascii=False)}

BLOG:
{blog}

केवल updated blog return करें।
"""

    response = client.responses.create(
        model="gpt-5",
        input=prompt
    )

    return response.output_text.strip()


# =========================================================
# INFORMATION TABLE HTML
# =========================================================

def create_information_table(rows):

    if not rows:
        return ""

    table = """
<h2>महत्वपूर्ण जानकारी</h2>

<table>
<thead>
<tr>
<th>जानकारी</th>
<th>विवरण</th>
</tr>
</thead>
<tbody>
"""

    for row in rows:

        label = str(
            row.get("label", "")
        ).strip()

        value = str(
            row.get("value", "")
        ).strip()

        if not label or not value:
            continue

        table += f"""
<tr>
<td><strong>{label}</strong></td>
<td>{value}</td>
</tr>
"""

    table += """
</tbody>
</table>
"""

    return table


# =========================================================
# INSERT TABLE INTO BLOG
# =========================================================

def insert_information_table(
    blog,
    table_html
):

    if not table_html:
        return blog

    # Placeholder replace
    placeholders = [
        "[यहाँ table placeholder रखें]",
        "[TABLE]",
        "[TABLE HERE]"
    ]

    for placeholder in placeholders:

        if placeholder in blog:

            return blog.replace(
                placeholder,
                table_html
            )

    # अगर placeholder नहीं मिला,
    # Introduction के बाद table insert करें

    lines = blog.splitlines()

    output = []

    inserted = False

    for line in lines:

        output.append(line)

        if (
            not inserted
            and line.strip().lower()
            in [
                "## introduction",
                "## परिचय"
            ]
        ):

            continue

        if (
            not inserted
            and line.startswith("## ")
            and "मुख्य जानकारी" in line
        ):

            output.insert(
                len(output) - 1,
                table_html
            )

            inserted = True

    if not inserted:

        # Safe fallback:
        # Blog ke beginning mein table
        output.insert(
            1,
            table_html
        )

    return "\n".join(output)


# =========================================================
# MARKDOWN TO HTML
# =========================================================

def markdown_to_html(markdown):

    html_lines = []

    for line in markdown.splitlines():

        line = line.strip()

        if not line:
            continue

        # Preserve table HTML
        if line.startswith("<table"):
            html_lines.append(line)
            continue

        if line.startswith("<h2"):
            html_lines.append(line)
            continue

        if line.startswith("<h3"):
            html_lines.append(line)
            continue

        if line.startswith("<tr"):
            html_lines.append(line)
            continue

        if line.startswith("<thead"):
            html_lines.append(line)
            continue

        if line.startswith("<tbody"):
            html_lines.append(line)
            continue

        if line.startswith("</table"):
            html_lines.append(line)
            continue

        if line.startswith("</thead"):
            html_lines.append(line)
            continue

        if line.startswith("</tbody"):
            html_lines.append(line)
            continue

        # H3
        if line.startswith("### "):

            html_lines.append(
                f"<h3>{line[4:]}</h3>"
            )

        # H2
        elif line.startswith("## "):

            html_lines.append(
                f"<h2>{line[3:]}</h2>"
            )

        # H1
        elif line.startswith("# "):

            continue

        # Existing HTML
        elif line.startswith("<"):

            html_lines.append(line)

        # Bullet
        elif line.startswith("- "):

            html_lines.append(
                f"<li>{line[2:]}</li>"
            )

        # Numbered list
        elif re.match(
            r"^\d+\.\s+",
            line
        ):

            text = re.sub(
                r"^\d+\.\s+",
                "",
                line
            )

            html_lines.append(
                f"<li>{text}</li>"
            )

        # Paragraph
        else:

            html_lines.append(
                f"<p>{line}</p>"
            )

    return "\n".join(html_lines)


# =========================================================
# CLEAN SLUG
# =========================================================

def clean_slug(slug):

    slug = slug.strip().lower()

    slug = slug.replace(
        " ",
        "-"
    )

    slug = re.sub(
        r"[^a-z0-9\-]",
        "",
        slug
    )

    slug = re.sub(
        r"-+",
        "-",
        slug
    )

    return slug.strip("-")


# =========================================================
# GENERATE FEATURED IMAGE
# =========================================================

def generate_featured_image(
    title,
    category
):

    prompt = f"""
Create a professional editorial featured image for a Hindi
Indian jobs and education blog.

Article title:
{title}

Category:
{category}

Requirements:

- Professional news/blog style
- Clean modern composition
- Relevant visual elements based on the article topic
- Suitable for a WordPress featured image
- 16:9 landscape composition
- No copyrighted logos
- No fake government seals
- No misleading official-looking documents
- No excessive text
- Do not include random people
- High quality
- Suitable for an Indian Hindi employment website
"""

    try:

        result = client.images.generate(
            model="gpt-image-2",
            prompt=prompt,
            size="1536x1024"
        )

        image_base64 = result.data[0].b64_json

        if not image_base64:
            return None

        image_bytes = base64.b64decode(
            image_base64
        )

        filename = "featured_image.png"

        with open(
            filename,
            "wb"
        ) as file:

            file.write(
                image_bytes
            )

        return filename

    except Exception as e:

        print(
            f"Image generation error: {e}"
        )

        return None


# =========================================================
# UPLOAD IMAGE TO WORDPRESS
# =========================================================

def upload_image_to_wordpress(
    image_path,
    title
):

    if not image_path:
        return None

    filename = os.path.basename(
        image_path
    )

    media_url = (
        f"{API_BASE}/media"
    )

    try:

        with open(
            image_path,
            "rb"
        ) as image_file:

            response = requests.post(
                media_url,
                headers={
                    "Content-Disposition":
                        f'attachment; filename="{filename}"',
                    "Content-Type":
                        "image/png"
                },
                data=image_file,
                auth=AUTH,
                timeout=60
            )

        if response.status_code != 201:

            print(
                "❌ Image upload failed:"
            )

            print(
                response.text[:1000]
            )

            return None

        media = response.json()

        media_id = media.get(
            "id"
        )

        # Update ALT text
        alt_text = (
            f"{title} - Featured Image"
        )

        requests.post(
            f"{API_BASE}/media/{media_id}",
            json={
                "alt_text": alt_text,
                "caption": title
            },
            auth=AUTH,
            timeout=30
        )

        return media_id

    except Exception as e:

        print(
            f"❌ Image upload error: {e}"
        )

        return None


# =========================================================
# UPDATE FEATURED IMAGE
# =========================================================

def set_featured_image(
    post_id,
    media_id
):

    if not media_id:
        return False

    response = requests.post(
        f"{API_BASE}/posts/{post_id}",
        json={
            "featured_media": media_id
        },
        auth=AUTH,
        timeout=30
    )

    return response.status_code == 200


# =========================================================
# UPDATE RANK MATH
# =========================================================

def update_rank_math(
    post_id,
    seo
):

    rank_math_url = (
        f"{BASE_URL}/wp-json/rankmath/v1/updateMeta"
    )

    payload = {

        "objectType":
            "post",

        "objectID":
            int(post_id),

        "meta": {

            "rank_math_title":
                seo.get(
                    "seo_title",
                    ""
                ),

            "rank_math_description":
                seo.get(
                    "meta_description",
                    ""
                ),

            "rank_math_focus_keyword":
                seo.get(
                    "focus_keyword",
                    ""
                )
        }
    }

    try:

        response = requests.post(
            rank_math_url,
            json=payload,
            auth=AUTH,
            timeout=30
        )

        return (
            response.status_code == 200
        )

    except Exception:

        return False


# =========================================================
# CREATE WORDPRESS DRAFT
# =========================================================

def create_wordpress_draft(
    blog,
    seo,
    image_path
):

    # -----------------------------------------------------
    # Category
    # -----------------------------------------------------

    categories = get_categories()

    ai_category = seo.get(
        "category",
        "Government Job"
    )

    category_id, category_name = (
        get_category_id(
            ai_category,
            categories
        )
    )

    if not category_id:

        raise Exception(
            "WordPress category nahi mili."
        )


    # -----------------------------------------------------
    # Tags
    # -----------------------------------------------------

    tag_ids = []

    for tag_name in seo.get(
        "tags",
        []
    ):

        tag_id = get_or_create_tag(
            tag_name
        )

        if tag_id:

            tag_ids.append(
                tag_id
            )


    # -----------------------------------------------------
    # Title
    # -----------------------------------------------------

    title = seo.get(
        "seo_title",
        "Hindi Blog"
    ).strip()


    # -----------------------------------------------------
    # Slug
    # -----------------------------------------------------

    slug = clean_slug(
        seo.get(
            "slug",
            ""
        )
    )


    # -----------------------------------------------------
    # HTML
    # -----------------------------------------------------

    html_content = markdown_to_html(
        blog
    )


    # -----------------------------------------------------
    # Create Post
    # -----------------------------------------------------

    post_data = {

        "title":
            title,

        "content":
            html_content,

        "status":
            "draft",

        "categories":
            [category_id],

        "tags":
            tag_ids,

        "slug":
            slug
    }


    response = requests.post(
        f"{API_BASE}/posts",
        json=post_data,
        auth=AUTH,
        timeout=30
    )


    if response.status_code != 201:

        raise Exception(
            f"WordPress Error: "
            f"{response.status_code} "
            f"{response.text[:1000]}"
        )


    post = response.json()

    post_id = post.get(
        "id"
    )


    # -----------------------------------------------------
    # Upload Featured Image
    # -----------------------------------------------------

    media_id = None

    if image_path:

        media_id = (
            upload_image_to_wordpress(
                image_path,
                title
            )
        )

        if media_id:

            set_featured_image(
                post_id,
                media_id
            )


    # -----------------------------------------------------
    # Rank Math
    # -----------------------------------------------------

    rank_math_success = (
        update_rank_math(
            post_id,
            seo
        )
    )


    return {

        "post_id":
            post_id,

        "title":
            title,

        "category":
            category_name,

        "slug":
            slug,

        "tags":
            tag_ids,

        "media_id":
            media_id,

        "rank_math":
            rank_math_success
    }


# =========================================================
# STREAMLIT UI
# =========================================================

st.set_page_config(
    page_title="PortalJobs AI Blog Agent",
    page_icon="🚀",
    layout="wide"
)


st.title(
    "🚀 PortalJobs Hindi AI Blog Agent"
)

st.caption(
    "URL → Research → Hindi Blog → Table → SEO → Links → Image → WordPress"
)


st.divider()


# =========================================================
# INPUT
# =========================================================

url = st.text_input(
    "🔗 Source Article URL",
    placeholder="https://example.com/article"
)


col1, col2, col3 = st.columns(3)


with col1:

    word_count = st.selectbox(
        "📝 Blog Length",
        [
            1000,
            1500,
            2000,
            2500,
            3000
        ],
        index=1
    )


with col2:

    use_links = st.checkbox(
        "🔗 Internal & External Links",
        value=True
    )


with col3:

    use_featured_image = st.checkbox(
        "🖼️ Generate Featured Image",
        value=True
    )


st.divider()


# =========================================================
# GENERATE
# =========================================================

if st.button(
    "🚀 GENERATE BLOG",
    type="primary",
    use_container_width=True
):

    if not url.strip():

        st.error(
            "❌ Source URL enter karein."
        )

        st.stop()


    try:

        with st.status(
            "AI Blog Agent working...",
            expanded=True
        ) as status:

            # ---------------------------------------------
            # ARTICLE
            # ---------------------------------------------

            st.write(
                "🌐 Source article read ho raha hai..."
            )

            source_title, source_content = (
                extract_article(
                    url
                )
            )


            if not source_content:

                raise Exception(
                    "Source article ka content nahi mila."
                )


            source_content = (
                source_content[:30000]
            )


            # ---------------------------------------------
            # IMPORTANT INFORMATION
            # ---------------------------------------------

            st.write(
                "📊 Important information extract ho rahi hai..."
            )

            information_rows = (
                extract_important_information(
                    source_title,
                    source_content
                )
            )


            # ---------------------------------------------
            # BLOG
            # ---------------------------------------------

            st.write(
                "✍️ Hindi blog generate ho raha hai..."
            )

            blog = generate_blog(
                source_title,
                source_content,
                information_rows,
                word_count
            )


            # ---------------------------------------------
            # TABLE
            # ---------------------------------------------

            st.write(
                "📋 Important Information table integrate ho rahi hai..."
            )

            table_html = (
                create_information_table(
                    information_rows
                )
            )

            blog = insert_information_table(
                blog,
                table_html
            )


            # ---------------------------------------------
            # SEO
            # ---------------------------------------------

            st.write(
                "🔍 SEO data generate ho raha hai..."
            )

            seo = generate_seo(
                blog
            )


            # ---------------------------------------------
            # LINKS
            # ---------------------------------------------

            internal_links = []
            external_links = []


            if use_links:

                st.write(
                    "🔗 Internal links find ho rahe hain..."
                )

                existing_posts = (
                    get_existing_posts()
                )

                internal_links = (
                    find_internal_links(
                        blog,
                        existing_posts
                    )
                )


                st.write(
                    "🌍 External/official links check ho rahe hain..."
                )

                available_external_links = (
                    extract_external_links(
                        url
                    )
                )


                external_links = (
                    select_external_links(
                        blog,
                        available_external_links
                    )
                )


                if internal_links or external_links:

                    st.write(
                        "🔗 Links article mein integrate ho rahe hain..."
                    )

                    blog = add_links_to_blog(
                        blog,
                        internal_links,
                        external_links
                    )


                        # ---------------------------------------------
            # FEATURED IMAGE
            # ---------------------------------------------

            image_path = None

            if use_featured_image:

                st.write(
                    "🎨 Featured image generate ho rahi hai..."
                )

                image_path = generate_featured_image(
                    seo.get(
                        "seo_title",
                        source_title
                    ),
                    seo.get(
                        "category",
                        "Government Job"
                    )
                )

            # ---------------------------------------------
            # WORDPRESS
            # ---------------------------------------------

            st.write(
                "📤 WordPress Draft create ho raha hai..."
            )

            result = create_wordpress_draft(
                blog,
                seo,
                image_path
            )


            # ---------------------------------------------
            # COMPLETE
            # ---------------------------------------------

            status.update(
                label="✅ Blog successfully created!",
                state="complete"
            )


        # =================================================
        # RESULT
        # =================================================

        st.success(
            "🎉 WordPress Draft successfully created!"
        )


        col1, col2, col3, col4 = st.columns(4)


        with col1:

            st.metric(
                "Post ID",
                result["post_id"]
            )


        with col2:

            st.metric(
                "Category",
                result["category"]
            )


        with col3:

            st.metric(
                "Internal Links",
                len(internal_links)
            )


        with col4:

            st.metric(
                "External Links",
                len(external_links)
            )


        st.divider()


        st.subheader(
            "📊 Important Information"
        )


        if information_rows:

            st.table(
                information_rows
            )

        else:

            st.info(
                "Important information table generate nahi hui."
            )


        st.subheader(
            "🎯 SEO Information"
        )


        st.write(
            "**SEO Title:**",
            seo.get(
                "seo_title",
                ""
            )
        )


        st.write(
            "**Meta Description:**",
            seo.get(
                "meta_description",
                ""
            )
        )


        st.write(
            "**Focus Keyword:**",
            seo.get(
                "focus_keyword",
                ""
            )
        )


        st.write(
            "**Slug:**",
            result["slug"]
        )


        st.write(
            "**Category:**",
            result["category"]
        )


        st.write(
            "**Tags:**",
            ", ".join(
                seo.get(
                    "tags",
                    []
                )
            )
        )


        if result["media_id"]:

            st.success(
                "🖼️ Featured image uploaded and assigned successfully."
            )

        else:

            st.warning(
                "⚠️ Featured image create/upload nahi hui."
            )


        if result["rank_math"]:

            st.success(
                "🎯 Rank Math SEO successfully updated."
            )

        else:

            st.warning(
                "⚠️ Rank Math update failed."
            )


        st.divider()


        st.subheader(
            "👀 Blog Preview"
        )


        st.markdown(
            blog
        )


        st.divider()


        st.info(
            "📝 WordPress post DRAFT hai. "
            "Automatically publish nahi hua."
        )


    except requests.exceptions.RequestException as e:

        st.error(
            f"❌ Connection error: {e}"
        )


    except Exception as e:

        st.error(
            f"❌ Error: {e}"
        )