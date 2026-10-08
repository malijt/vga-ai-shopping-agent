# Privacy note: what happens to a shopper's photo

Written 2026-10-08 for the owner of the demo. It describes the code as it was at commit `3e480f6`
(the one before this note) and what the audit in `tests/guards/privacy/` checks. It is an
engineering note, not legal advice.

Every statement is one of three kinds, and the text says which:

- **Checked by the audit**: a test fails if it stops being true. Run it with
  `uv run pytest tests/guards/privacy`.
- **Read in the code or in the vendor's documentation**: I read it and give the place. Nothing
  runs to confirm it.
- **Not verified**: I could not check it. It is listed again at the end.

## In short

- The photo is never saved by the app: not as a file, not in a log, not in a cache. **Checked.**
- The photo and the words you type go to **OpenAI**, and nowhere else. The stores never get the
  photo. **Checked.**
- Before the photo is sent, the app draws it again as a smaller JPEG, which drops the camera
  details, the GPS position, the colour profile and any text comment in the file. **Checked.** It
  does not blur faces. See "What is removed".
- The app asks OpenAI not to store the request. OpenAI may still keep it for a time, unless the
  account has OpenAI's "zero data retention". That is an account setting the owner has to ask OpenAI
  for. See "What OpenAI does with it".
- Two debug switches, `VGA_LOG_PROMPTS` and `VGA_DEBUG_DUMP`, are off by default and must stay off
  outside debugging. Neither writes the photo, but they write other things about the shopper.
- Before real shoppers use this, a legal review is needed (UAE data protection law, GDPR if people
  in Europe use it, each store's terms). This note does not replace it.

## What leaves the computer

| What | Where to | Why | Status |
|---|---|---|---|
| The photo, as a smaller JPEG (at most 1024 pixels on the long side) | OpenAI | The AI reads what garments are in it | Checked |
| The words you typed | OpenAI | Same | Checked |
| Short search words, for example "black oversized blazer" | The stores being searched | To find products | Checked |
| A request for each product's picture | The stores' image servers | To compare products with the photo | Checked |
| The app's name `vga-shopping-agent-demo/0.1 (store search demo)` and the computer's internet address | The stores | Every web request carries them | Read in the code |

Details that matter:

- **The photo goes only to OpenAI.** The audit looks at every request the app makes to a store or an
  image server (the address, the headers, the body) and finds no trace of the photo, nor a body of
  any kind. The photo is in the request to OpenAI exactly once, in one place, as an image.
- **A failed call is tried once more**, and the photo goes with it. A request can therefore send the
  photo to OpenAI twice. Never more.
- **The stores get search words, not the photo.** Those words are what the AI wrote after reading
  your photo and text. If OpenAI cannot be reached and you also typed text, the app falls back to
  your own words and tells you so ("we searched with your words as typed"): then what you typed goes
  to the stores. The photo is not used in that case. **Checked.**
- **No cookies** are sent to or kept from the stores, and no browser is imitated. Read in
  `src/vga/fetch/client.py`.
- **Nothing is sent to the people who make Streamlit.** `.streamlit/config.toml` turns their usage
  statistics off. Read in the file. Not verified on a running page.
- **The image model runs on this computer.** The one download of its weights (from Hugging Face)
  happens once, ahead of time, and carries no shopper data. During a search the weights are only
  looked up locally. Read in `src/vga/rank/image/model.py`.
- **Clicking a result** takes you to the store's own site. From there the store's own privacy rules
  apply, not this note.

## What OpenAI does with it

The app asks OpenAI not to keep the request: every call sets `store` to false. **Checked**, for
every call including the repeat.

That is not the same as OpenAI keeping nothing. OpenAI's page on data controls
(`developers.openai.com/api/docs/guides/your-data`, read on 2026-10-08) says, in summary:

- Logs used to watch for misuse hold prompts and responses and are kept for up to 30 days by default.
- **Zero data retention** is a separate arrangement. It needs OpenAI's prior approval and extra
  terms. Once approved it is set for the organisation or for one project, under Settings,
  Organization, Data controls. With it on, `store` is treated as false whatever the request says.
- The Responses API, which this app uses, is covered by it, with exceptions. The page names one that
  concerns photos: image and file inputs are scanned for child-sexual-abuse material, and are kept
  if flagged, even with zero data retention on.

What the owner has to do: ask OpenAI for zero data retention for the organisation or project that
owns the key, if the demo is to go beyond testers who accept the default. I did not sign in to
OpenAI, so **whether this account has it is not verified**, and so is exactly which steps the
request takes. The plan (assumption A10) records that the key's current retention setting is
accepted for the demo.

The page the shopper sees says: "Your photo is sent to OpenAI for analysis and is not stored by us."
That is true of the app. It says nothing about OpenAI's side, so it should be reworded once the
retention question above is decided.

## What is removed from the photo, and what is not

Before sending, the app opens the photo, turns it upright (using the camera's rotation tag, then
forgets the tag), shrinks it to at most 1024 pixels on the long side and saves a new JPEG built
from the pixels alone, so nothing else in the file can travel with it. **Checked** with JPEG, PNG and WebP photos that hide a marker in each place below:

| Removed | Not removed |
|---|---|
| Camera make and model, the description, the date (the EXIF block) | **The picture itself**: any people and faces, text on clothes or signs, the room, the street |
| The GPS position | |
| The embedded colour profile | |
| A text comment inside the file (a JPEG comment, or a PNG text note named `comment`) | |
| XMP packets, other PNG text notes, anything after the end of the picture | |

Two things to know:

1. **Faces are not blurred or removed.** There is no face detection anywhere in the code. A photo of
   a person, a group or a child goes to OpenAI as it is. An outfit photo is usually a photo of a
   person.
2. **A comment used to be sent; fixed on 2026-10-08.** The audit found that a JPEG comment, or a
   PNG text note named `comment`, went out with the photo, because the picture library copied it
   into the new file. The outgoing JPEG is now built from the pixels alone, and the audit's two
   tests for it (`test_nothing_but_the_picture_goes_to_openai[JPEG comment]` and
   `[PNG text chunk named comment]`) pass.

## What stays in memory, and for how long

| What | Where | How long | Status |
|---|---|---|---|
| The photo, during a search | The search program's memory | Until the search ends. Nothing in the search program refers to it afterwards | Checked |
| The photo, in the upload box of the page | The page's server memory, kept by Streamlit (not on disk) | Until the search that used it ends: the page then resets the upload box, so its own state holds no photo (plan item 15.1.2, built 2026-10-08). Streamlit's own store drops a session's uploads when the session is removed | The page's state is checked by tests. When Streamlit's own store lets go of the file after the box is reset is read from Streamlit 1.65.0's source, not verified on a running page |
| The photo's **embedding**: a list of numbers that describes how the photo looks | The search program's memory (the "search again" cache), and the page's session | The cache keeps the latest 32 searches until the program stops, or a newer search pushes the oldest out. The 10-minute limit only decides whether the stored store results can be re-used; it does not delete anything | Checked (it is numbers only); lifetime read in `src/vga/pipeline/rerun.py` |
| What the AI read in the photo (colour, style, search words) | The same places, and in the answer shown on the page | The same | Checked that it holds no image |
| The stores' answers | The search program's memory | 10 minutes for re-use | Read in the code |
| Product pictures (thumbnails) | Not kept. Fetched, compared, dropped | | Checked |

Why the embedding is kept: when the shopper edits a chip and searches again, the app reuses the
numbers instead of needing the photo. It is the only trace of the photo the app holds after a
search. **I could not verify whether such numbers can be turned back into a recognisable picture.**
Treat them as personal data that comes from the photo.

What I could not look at: the real image model's memory. The audit uses a stand-in because the model
needs the optional `ml` packages. The code of the real one (`SiglipEmbedder.embed`) keeps nothing
after it returns. **Read, not run.**

## What is written to disk

By default, only this: **`logs/vga.jsonl`**, one line per event. At the default level it holds the
request number, step timings, store names and outcomes, the AI model's name and the prompt version,
the number of tokens, and whether a photo was sent (yes or no). It holds no photo and, when the AI
answered, no typed words. **Checked.**

The **search words** (what the AI wrote after reading the photo, or your own words in the fallback)
get into the log in a few cases even at the default level, because those log lines carry the
store's web address, which contains them: a store blocks us or does not answer in time, a search is
answered from the memory of an earlier identical one, or a store's `robots.txt` refuses a page.
Read in `src/vga/stores/engine.py`, `src/vga/fetch/client.py` and `src/vga/fetch/robots.py`. At the
`DEBUG` level every store search is logged that way. **Checked.**

- The app never deletes or rotates this file, and puts no limit on its size. Read in `src/vga/log.py`.
- It is created with the account's usual file permissions; the app sets none. Read in the code.
- `logs/` is in `.gitignore`, so it is not committed.
- The command line (`python -m vga.search --image photo.jpg`) reads the photo from the file you
  name and never changes or copies that file. **Checked.**

The photo itself is never written. The audit watches every file the program opens for writing while
a request runs, the folders it could write to, and the temporary folder; the only files that change
are the log and, if switched on, the dump. **Checked.**

## The two debug switches

Both are **off** in the code, in `config/settings.yaml` and in `.env.example`. **Checked.** They
are meant for a developer who is looking at one search to see why the results came out as they did.

**`VGA_LOG_PROMPTS=1`** adds two things to the log:

- the words the shopper typed, exactly as typed;
- what the AI read: the garments, colours and styles, the guessed gender, and the price limit. For a
  photo-only search this is a description of what is in the photo.

It never writes the photo. **Checked** under every combination of the two switches. With it off, and
the AI answering, the typed words are not in the log. **Checked.**

**`VGA_DEBUG_DUMP=1`** writes one more file per search, `logs/candidates-<request number>.jsonl`,
listing every product considered: its link, store, title, price, scores and which price range it was
shown in. It holds nothing about the shopper, no typed words and no image data. **Checked.**

Why they should stay off outside debugging: both pile up on the disk with no limit and no deletion,
and the first one records what a person asked for and, for a photo, what the AI saw in it. A person's
requests can be personal data on their own.

Two more rules for whoever runs the app:

- **Never turn on debug logging for the whole Python process** (for example
  `logging.basicConfig(level=DEBUG)`). The library that reads the photo, Pillow, then writes the text
  fields of the photo's EXIF block (such as the description and the camera make) to the log. I saw
  this once with Pillow 12.3.0; it is not a test, because it is the library's behaviour and not the
  app's. The app's own `VGA_LOG_LEVEL=DEBUG` does not do this. **Checked.** The OpenAI library and
  httpx, at debug level, do not log the photo. **Checked**, and the test will fail if an upgrade
  changes that. The GPS position did not appear in what Pillow logged while reading the photo in that run.
- Streamlit's own `--logger.level` only affects Streamlit's loggers. Read in Streamlit 1.65.0's
  source.

## What the audit proves, and what it cannot see

The audit runs whole searches through the real search pipeline and the real OpenAI library. Only the
outside world is faked: the stores' web servers, OpenAI's server, the image model's weights and the
clock. The searches are: one garment; a photo with text; an outfit; a PNG and a WebP photo; a search
again after a chip edit; an answer from OpenAI that is cut off and asked again; a store that blocks
us; the image model crashing; the deadline passing while the products are compared, and while
waiting for OpenAI; OpenAI unreachable (with and without text); OpenAI refusing the key or the
request; and three kinds of file that are not photos. The first three (one
garment, photo with text, outfit) run under all four settings of the two switches; the rest with
both on.

For each, it checks the files written, every log call, everything still reachable in memory
afterwards, every request leaving the computer, and what the caller gets back (the answer, the saved
settings for "search again", the error).

It would be useless if it could not fail, so there are tests that put 23 deliberate privacy bugs into
the app (a copy of the photo in the working folder, a shrunk copy, the photo in a log line the logger
hides, in a cache, in a variable of a function, in a header sent to a store, a connection to another
server, a second program started) and require the audit to catch each one.

What it **cannot** see:

- Memory that is not Python objects: the pixel buffers inside the imaging library, and what the
  operating system leaves in swap files, crash reports or backups.
- A file written by code that does not go through Python's file functions (a C library that opens a
  file itself). The before-and-after look at the folders catches that only for the folders it
  watches, and not if the file is deleted again.
- The real image model's inner workings (read, not run), and a running Streamlit page: the audit
  covers the search pipeline and the command line (`python -m vga.search --image ...`). The page
  has run the real search since 2026-10-08, and its own tests check that it holds no photo after a
  search, but the audit's five-channel watch has not been run against a live page.
- What the browser keeps of an uploaded file, a terminal's scrollback if log lines are shown there,
  and OpenAI's side of the connection.
- A search more than a few minutes after the first, or a program that has run for days.

It shows that the app, as it is today, does not keep the photo in the places that were looked at. It
does not show that nothing can.

## Before real shoppers use this

None of this is decided here. A person who can give legal advice should look at:

- **UAE data protection law**: Federal Decree-Law No. 45 of 2021 (the PDPL). Whether a photo of a
  person is personal data, what notice and consent a shopper must be given, and the rules on sending
  personal data out of the UAE (OpenAI processes the photo outside the UAE, probably in the United
  States: **not verified**).
- **GDPR** (Regulation (EU) 2016/679), if people in Europe use the demo.
- **OpenAI**: the zero data retention decision above, and the contract terms for the API.
- **Each store's terms of use**. The demo reads the stores' public search pages; product rule 6
  says to check their terms before real users. Not done.
- **The wording on the page** about the photo (see above), and a way for a shopper to ask for their
  data to be deleted: there is nothing to delete today except the log files, which the owner would
  have to clear by hand.
- **Photos of other people**, children in particular, uploaded by someone who is not them.
- **Hosting**: today everything runs on one computer. A hosted version keeps these logs, this
  memory and Streamlit's uploads on a server, and the rules in this note would need to be checked
  again.

## Not verified

- Whether this OpenAI account has zero data retention, and the exact steps to request it.
- Whether the embedding of a photo can be turned back into a picture.
- That the real image model keeps nothing of its input (code read, model not run).
- Streamlit's own upload handling on a running page, after the page has reset its upload box
  (built and tested on the page's side).
- Where OpenAI processes and stores the photo, and the legal position under the UAE law and GDPR.
- That Streamlit really sends no usage statistics (the setting is in the file), and exactly when it
  drops an uploaded file from memory.
- The store pages' own terms.

## Where each statement is checked

| Statement | Test in `tests/guards/privacy/` |
|---|---|
| Nothing leaves a trace in files, logs, memory, requests or answers | `test_no_retention.py` |
| The audit can fail | `test_canaries.py`, `test_instruments.py` |
| What is stripped before sending, including a file comment; `store` is false | `test_sent_photo.py` |
| What the switches write; the libraries do not log the photo | `test_debug_switches.py` |
| The "search again" cache; no thumbnail cache | `test_caches.py` |
| The command line | `test_cli.py` |
