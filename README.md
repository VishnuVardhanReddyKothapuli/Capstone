# Sentinal

NSFW image classification and duplicate detection over one upload, with a FastAPI
backend and a React + TypeScript frontend.

Two independent checks run against an image:

| Check | Model | Store | Output |
| --- | --- | --- | --- |
| **NSFW** | `Falconsai/nsfw_image_detection` (2-class ViT) | — | one `nsfw` probability, placed in a green / amber / red band |
| **Similarity** | `openai/clip-vit-base-patch32` (512-dim) | ChromaDB | cosine score against every stored image, plus the closest match |

Each check keeps its own verdict. The overall verdict on a card is the **more
severe** of the two.

On top of those, an optional third opinion: **"Why this verdict?"** asks Google
Gemini to describe what is visibly in the image, read any text in it, and say in
words whether it may be published. It is opt-in per check, never changes the
verdict above it, and is switched off entirely without an API key.

---

## Layout

```
capstone/
├── backend/
│   ├── app/
│   │   ├── config.py          all tuning in one place (env-overridable)
│   │   ├── database.py        SQLAlchemy engine, session, init_db()
│   │   ├── models.py          users + checks tables
│   │   ├── schemas.py         Pydantic request/response models
│   │   ├── security.py        bcrypt hashing, JWT issue/decode
│   │   ├── deps.py            DbSession / CurrentUser dependencies
│   │   ├── main.py            app wiring, CORS, SPA hosting
│   │   ├── routers/           auth, moderate, explain, history, meta
│   │   └── services/
│   │       ├── images.py      decode, sniff type, sample GIF keyframes, thumbnail
│   │       ├── classifier.py  Falconsai pipeline (lazy)
│   │       ├── embedder.py    CLIP embeddings (lazy)
│   │       ├── explainer.py   Gemini second opinion + score normalisation
│   │       ├── vector_store.py ChromaDB collection
│   │       ├── similarity.py  neighbour search -> band + match
│   │       └── tiers.py       pure band/severity logic
│   ├── tests/                 128 tests, real SQLite + real Chroma
│   ├── requirements.txt
│   └── .env.example
└── frontend/
    └── src/
        ├── api/client.ts      typed fetch wrapper, token handling
        ├── auth/              AuthContext + LoginScreen
        ├── components/        Dropzone, ResultCard, ExplainBox, TierBadge, Metric, …
        ├── views/             Home, Check, History, About, Stack
        ├── router.ts          History API routing, no dependency
        └── styles/            tokens.css + global.css (everything else is CSS Modules)
```

---

## Setup

Requires Python 3.11+ and Node 20+.

### Backend

```bash
cd backend
python -m venv .venv
.venv/Scripts/activate        # Windows;  source .venv/bin/activate elsewhere
pip install torch==2.14.0 torchvision==0.29.0 --index-url https://download.pytorch.org/whl/cpu
pip install -r requirements.txt
cp .env.example .env
```

Installing torch from the CPU index first matters: the PyPI wheel pulls ~2.5 GB of
CUDA libraries that a CPU-only machine never uses.

Then set a real signing key in `backend/.env` — the built-in default is a known
string and the server logs a warning while it is in use:

```bash
python -c "import secrets; print(secrets.token_urlsafe(48))"
```

Optionally add a Gemini key to the same file to switch on the "Why this verdict?"
box. Without one, both local checks work exactly as before and the explain
endpoint answers `503`:

```
GEMINI_API_KEY=your-key-from-https://aistudio.google.com/apikey
```

### Frontend

```bash
cd frontend
npm install
```

---

## Running

Two processes in development, so Vite can hot-reload:

```bash
cd backend && uvicorn app.main:app --reload --port 8000
```

```bash
cd frontend && npm run dev
```

Open http://localhost:5173. Vite proxies `/api` and `/health` to port 8000.

For a single-process deployment, build the frontend and let FastAPI serve it:

```bash
cd frontend && npm run build
cd ../backend && uvicorn app.main:app --port 8000
```

Now http://localhost:8000 serves the app, and any unknown path falls back to
`index.html` so a refresh on `/history` still works. Interactive API docs are at
`/docs`.

**First check is slow.** Models are downloaded on demand — roughly 350 MB for the
classifier and 600 MB for CLIP — and cached under `~/.cache/huggingface`. Later
checks reuse the in-memory model.

---

## How a check works

One `POST /api/moderate` does all of it: read the upload under a hard size cap,
decode it and **sniff** the real type from the bytes (the filename is not
trusted), sample up to 16 keyframes if it is animated, run whichever checks the
`mode` asked for, write one row to SQL, add one vector to Chroma if the mode
embeds, and return a single verdict object.

### NSFW banding

Falconsai returns two probabilities that sum to 1 — `normal` and `nsfw`. Only
the `nsfw` one is banded:

| Band | Condition | Colour |
| --- | --- | --- |
| `explicit` | `nsfw >= 0.70` | red |
| `suggestive` | `0.40 <= nsfw < 0.70` | amber |
| `safe` | `nsfw < 0.40` | green |

Amber is a **confidence window, not a content category**. The model has no
"suggestive" class; that band is the range where it declines to commit, and it
is the one to route to a human.

Animations aggregate with `max`: every sampled frame is classified and the worst
frame decides the verdict, so one explicit frame cannot hide behind 59 safe
ones. `safe_score` is the complement of *that same frame's* score, so the pair
stays a real two-class softmax rather than a mix of numbers from different
frames. The card's `frames n/m` says how much of the file was actually looked
at.

### Similarity banding

CLIP maps the image to a 512-dim unit vector, Chroma returns cosine distance,
and the reported score is `1 - distance` clamped to `[0, 1]`.

| Band | Score | Severity |
| --- | --- | --- |
| Identical | `>= 0.98` | red |
| Near-Duplicate | `>= 0.92` | red |
| Similar | `>= 0.80` | amber |
| Slightly Similar | `>= 0.60` | green |
| Unique | below `0.60`, or an empty corpus | green |

`0.60` doubles as the match floor: under it a neighbour is not counted at all,
which is why `Unique` covers both "nothing close" and "nothing stored yet".

An animation is embedded as the renormalised mean of its per-frame unit vectors
— one equal vote per frame, so a GIF stays near visually identical GIFs without
a single outlier frame dominating.

When a check runs both, the card's overall verdict is the **more severe** of the
two: `Identical` is red even at `nsfw = 0.001`, and an explicit image is red even
if nothing like it has been seen before.

### Explaining a verdict

Both checks above produce numbers. Neither can say *why*. `POST
/api/checks/{id}/explain` sends one frame to Gemini with a fixed instruction —
describe what is visibly present, read any embedded text, pick one of `safe`,
`suggestive`, `nsfw`, `violent`, `hate`, and state whether publishing should be
blocked — and returns a five-way score distribution plus two short paragraphs.
Only `safe` is allowed to publish.

The answer is not trusted as given. The instruction asks for scores in `[0, 1]`
totalling ~1, a `classification` equal to the argmax, and a `confidence` equal to
that class's score; when the model breaks one of those rules the server repairs
it deterministically instead of trusting or rejecting the answer, and sets
`repaired: true` so the card can say so:

- unreadable and negative scores become `0`, then all five are rescaled to total
  1 — which also fixes an answer given in percentages;
- if the stated class disagrees with the argmax, the **less publishable** of the
  two wins;
- `confidence` is recomputed from the winning class;
- `publish_allowed` is derived from the class, never read from the prose.

It is a **cross-check, not an input**: the explanation never moves
`overall_tier`. If Gemini says `hate` and the local classifier says `safe`, the
card shows both and flags the disagreement rather than resolving it. The verdict
is stored on the row, so reopening it from History costs no API call, and
`?refresh=true` forces a new one.

Gemini's own safety filters are set to `BLOCK_NONE` for this call. This *is* the
moderation tool — an image that trips those filters is exactly the image a
moderator needs described. Blocking is decided by the classification asked for,
not by the transport; if Gemini refuses anyway, the endpoint answers `422` and
the local verdict stands on its own.

---

## Storage

Two stores, each holding only what it is good at:

| | SQL (SQLite or MySQL) | ChromaDB |
| --- | --- | --- |
| Holds | users, original bytes, 256 px thumbnail, both verdicts, the thresholds in force at the time, the cached Gemini explanation | 512-dim CLIP vectors, nothing else |
| Keyed by | `checks.id` | the same `checks.id`, as the Chroma document id |
| Answers | History, blob serving, auth | nearest-neighbour search |

`models.py` has no embedding column, and Chroma stores no image bytes. Because a
vector's id *is* the SQL row id, a neighbour hit resolves back to its row with
one primary-key lookup, and `similarity_match_check_id` is a real foreign key
rather than a loose reference.

Two consequences worth knowing:

- An `nsfw`-only check is never embedded. It gets a SQL row but no vector, so
  later uploads can never match it. This is why CLIP is not even loaded for that
  mode.
- Deleting a check row would not remove its vector — there is no delete endpoint
  yet.

---

## API

Everything under `/api` requires `Authorization: Bearer <token>`; `/health` does
not. Interactive docs at `/docs`.

| Method | Path | Notes |
| --- | --- | --- |
| `GET` | `/health` | liveness, plus whether a built frontend was found |
| `POST` | `/api/auth/register` | new account, returns a token — `409` if the name is taken |
| `POST` | `/api/auth/login` | credentials for a token |
| `GET` | `/api/auth/me` | the current account |
| `POST` | `/api/moderate` | multipart `file` + `mode` (`nsfw` \| `similarity` \| `both`) |
| `POST` | `/api/checks/{id}/explain` | Gemini's written second opinion, **owner only**; `?refresh=true` re-asks |
| `GET` | `/api/history` | own checks, newest first — `check_type`, `limit` (≤100), `offset` |
| `GET` | `/api/checks/{id}` | one own check (`404` for anyone else's) |
| `GET` | `/api/checks/{id}/thumbnail` | JPEG, readable by any signed-in user |
| `GET` | `/api/checks/{id}/image` | original bytes, **owner only** (`403` otherwise) |
| `GET` | `/api/models` | live models / thresholds / store report — what the Stack page renders |

Upload rejections: `413` over `MAX_UPLOAD_BYTES`, `415` for anything Pillow
cannot decode, `400` for an empty file, `422` for an unknown `mode`, and `503`
if a model or the vector store fails to come up.

Explain failures each get their own status, so the box can say something useful:
`503` no API key configured, `422` Gemini declined to analyse the image, `429`
rate limited, `504` timed out, `502` anything else upstream — including a
rejected key, which is reported without echoing Google's response body, since
that body can quote the key back.

---

## Configuration

Every value lives in `backend/app/config.py` and can be overridden from
`backend/.env` or the environment. Relative paths in the config resolve against
`backend/`, so the app behaves the same whichever directory uvicorn is launched
from.

| Variable | Default | Purpose |
| --- | --- | --- |
| `DATABASE_URL` | `sqlite:///backend/sentinal.db` | any SQLAlchemy URL; `mysql+pymysql://…` also needs `PyMySQL` |
| `CHROMA_PERSIST_DIR` | `backend/chroma_db` | on-disk vector store |
| `CHROMA_COLLECTION` | `image_embeddings` | collection name |
| `JWT_SECRET` | dev placeholder | **replace before exposing the service** |
| `JWT_EXPIRE_MINUTES` | `720` | 12 hours |
| `NSFW_MODEL` | `Falconsai/nsfw_image_detection` | any 2-class HF image classifier |
| `NSFW_EXPLICIT_THRESHOLD` | `0.70` | red at or above |
| `NSFW_SUGGESTIVE_THRESHOLD` | `0.40` | amber at or above |
| `CLIP_MODEL` | `openai/clip-vit-base-patch32` | changing the dimension needs a re-index |
| `SIMILARITY_TOP_K` | `5` | neighbours fetched for the match |
| `SIMILARITY_COUNT_K` | `50` | neighbours scanned when counting matches |
| `SIM_*_THRESHOLD` | `0.98 / 0.92 / 0.80` | the similarity band edges |
| `SIM_MATCH_FLOOR` | `0.60` | below this, not a match at all |
| `MAX_GIF_FRAMES` | `16` | keyframe cap per animation |
| `MAX_UPLOAD_BYTES` | `10485760` | 10 MiB |
| `THUMBNAIL_SIZE` | `256` | longest edge, px |
| `GEMINI_API_KEY` | empty | empty = explanations off; the endpoint answers `503` |
| `GEMINI_MODEL` | `gemini-2.5-flash` | any model that accepts an image and honours a response schema |
| `GEMINI_TIMEOUT_SECONDS` | `45` | one request, no retry |
| `GEMINI_MAX_IMAGE_EDGE` | `1024` | frame is downscaled to this longest edge before being sent |
| `CORS_ORIGINS` | Vite dev origins | only needed while the frontend runs on its own port |
| `FRONTEND_DIST` | `frontend/dist` | served at `/` when it exists |

Because `NSFW_MODEL` is only ever asked for its `nsfw`/`normal` probability, a
different binary checkpoint drops in without code changes. A model with a
different label set will raise rather than silently mis-score.

---

## Tests

```bash
cd backend
pytest -q
```

128 tests, and they are not heavily mocked: each one runs against a real
temporary SQLite file and a real temporary Chroma collection, so the cosine
maths, the banding, the SQL writes and every route are genuinely exercised. Only
the two neural nets are stubbed — `conftest.py` redirects `DATABASE_URL` and
`CHROMA_PERSIST_DIR` into a temp directory *before* `app.config` is imported, so
a run can never touch development data.

`tests/test_embedder.py` is the deliberate exception: it stubs the model but
uses real torch tensors, pinning the pooling and normalisation contract that the
faked `embed()` elsewhere would otherwise hide.

No test reaches the Gemini API. `conftest.py` sets `GEMINI_API_KEY=""` in the
environment, which overrides any value in `backend/.env`, so the feature is off
unless a test switches it on with a fake key and a stubbed `httpx.post`. That
means a full run cannot bill a real key even on a machine that has one
configured.

---

## Design decisions

Choices that are not obvious from the code, and what each one costs:

- **Thumbnails are readable by any signed-in user; originals are not.** A
  similarity result has to show what it matched, and the match usually belongs to
  someone else. A 256 px thumbnail is the smallest thing that makes the verdict
  reviewable, so that is what is shared; the full-size original returns `403` to
  anyone but its uploader.
- **Similarity search is global, History is per-user.** Duplicate detection
  scoped to a single account would find almost nothing. The corpus is shared; the
  audit trail is not.
- **The amber band is an admission of uncertainty.** With a binary model, the
  honest thing to do with a 0.55 score is say so, rather than invent a
  "suggestive" class the model never emitted.
- **Verdicts store the threshold in force.** `nsfw_threshold` is written into the
  row, so editing `.env` later cannot silently rewrite the meaning of old
  results.
- **`match_count` saturates at `SIMILARITY_COUNT_K = 50`.** It counts neighbours
  above the floor among the 50 nearest, not across the whole index, so `50` reads
  as "at least 50". Scanning the full collection for a display number is not
  worth the query.
- **CLIP similarity is semantic, not cryptographic.** It catches re-encodes,
  crops and rescales that a file hash would miss, and it will also score two
  different photographs of the same subject highly. It is a triage signal, not
  proof of a re-upload.
- **Tokens live in `localStorage`.** They survive a refresh, and they are
  readable by any script on the page. An httpOnly cookie would be stronger and
  would need CSRF handling; this is the trade-off a coursework-scale app makes
  knowingly.
- **`JWT_SECRET` must be changed before the service is reachable by anyone
  else.** The built-in default is a published string, and the server logs a
  warning at startup for as long as it is in use. Replacing it invalidates every
  token already issued.
- **Models load lazily, on first use.** Startup and `/health` stay fast; the
  first check pays the download. `/api/models` reports `loaded` per model so the
  Stack page can tell you which ones are warm.
- **Image bytes go in the database, not on disk.** One store to back up, no
  orphaned files, and it works unchanged against MySQL — at the cost of a heavier
  table. `LargeBinary(16_777_215)` is what maps to MySQL `MEDIUMBLOB`; plain
  `BLOB` caps at 64 KiB and would truncate uploads silently.
- **Two transformers-5 accommodations.** `get_image_features` now returns a
  pooling object rather than a tensor, and `AutoImageProcessor` hard-requires
  torchvision, so `embedder.py` reads `pooler_output` defensively and asks for
  `CLIPImageProcessor` by name. `torchvision` is pinned anyway, because it
  provides the faster image path.
- **Asking for an explanation uploads that image to Google.** The two local
  checks never leave the machine; this one cannot. That is why it is a separate
  endpoint the owner has to trigger, why it is off entirely without a key, and
  why the box says what it does before you press the button. It also costs money
  per request and is slower than both local models together, so it is not on the
  upload path.
- **The explanation is stored, not recomputed.** One column of opaque JSON on the
  `checks` row. The reasoning becomes part of the audit trail, reopening a
  History entry is free, and nothing queries inside it — the shape belongs to the
  explainer service, not to the schema.
- **A disagreement is shown, not resolved.** Gemini's five classes are wider than
  the local classifier's two, so it can name violence or hate that Falconsai
  cannot see — and it can also be wrong. Letting it move `overall_tier` would
  make one opinion silently overwrite the other, so the card displays both and
  says they differ.
- **Schema changes are applied additively at startup.** `create_all` creates
  missing tables but never adds columns to an existing one, so an install that
  predates the explanation feature would otherwise fail on every query.
  `database.py` inspects the live table and issues `ALTER TABLE … ADD COLUMN` for
  what is missing. Adding columns only — nothing is ever renamed or dropped —
  which is as far as this can safely go without a migration tool.





# Capstone
