import page from './Page.module.css'
import styles from './StaticPage.module.css'

/** Plain explanation of what the app does and, more importantly, what it does not. */
export function AboutView() {
  return (
    <div className={page.page}>
      <header className={page.header}>
        <span className={page.eyebrow}>About</span>
        <h1 className={page.title}>What Sentinal does</h1>
        <p className={page.subtitle}>
          Two independent checks over one uploaded image: a not-safe-for-work classification and a
          duplicate search. Each check keeps its own verdict, and the card shows the more severe of
          the two. A third, optional box explains the result in words.
        </p>
      </header>

      <section className={styles.section}>
        <h2 className={styles.sectionTitle}>The NSFW check</h2>
        <p className={styles.body}>
          The classifier is a two-class model: it answers <strong>nsfw</strong> or{' '}
          <strong>normal</strong>, and the two probabilities sum to 1. A single number is a poor
          basis for a yes/no decision near the middle, so the score is placed in one of three bands.
          Below the suggestive threshold is green, above the explicit threshold is red, and the gap
          between them is amber — not a content category, but an admission that the model is
          undecided and a person should look.
        </p>
        <p className={styles.body}>
          Animated GIFs are sampled at evenly spaced keyframes and scored on their{' '}
          <strong>worst</strong> frame, because one explicit frame makes the whole file explicit.
          The card reports how many frames were scored out of how many exist.
        </p>
      </section>

      <section className={styles.section}>
        <h2 className={styles.sectionTitle}>The similarity check</h2>
        <p className={styles.body}>
          CLIP converts the image into a 512-dimension unit vector. Chroma stores those vectors and
          returns the nearest ones by cosine distance; a distance is turned back into a similarity
          score. Above 0.98 the images are effectively the same file, and the bands step down from
          there to 0.60, below which nothing is reported.
        </p>
        <ul className={styles.list}>
          <li>
            The search is <strong>global</strong>: a duplicate is found even when someone else
            uploaded the original, and the match card names them.
          </li>
          <li>
            History is <strong>per account</strong>. You never see another account&apos;s list, only
            the one thumbnail of an image you matched.
          </li>
          <li>
            An NSFW-only check is never embedded, so it never joins the corpus and cannot be matched
            later. Use <strong>Similarity</strong> or <strong>Both</strong> to add an image.
          </li>
        </ul>
      </section>

      <section className={styles.section}>
        <h2 className={styles.sectionTitle}>Why this verdict?</h2>
        <p className={styles.body}>
          Both checks above produce numbers, and neither can say <em>why</em>. Under every result
          there is a box that asks a multimodal model (Google Gemini) to describe what is visibly in
          the image, read any text in it — signs, captions, memes, screenshots — and state in words
          whether it may be published. It answers with one of five classes:{' '}
          <strong>safe</strong>, <strong>suggestive</strong>, <strong>nsfw</strong>,{' '}
          <strong>violent</strong> or <strong>hate</strong>. Only <strong>safe</strong> is allowed to
          publish.
        </p>
        <ul className={styles.list}>
          <li>
            It is a <strong>second opinion, not an override</strong>. The verdict above never changes.
            When the two disagree — Gemini can see hate symbols and violence that a two-class NSFW
            model cannot — the box says so and leaves the decision to you.
          </li>
          <li>
            Asking sends that one frame <strong>to Google</strong>. The two local checks never leave
            the server, so this is opt-in per image and only ever runs when you press the button.
          </li>
          <li>
            The answer is saved with the check, so reopening it from History is free. Press{' '}
            <strong>Ask again</strong> to force a fresh one.
          </li>
          <li>
            Its own scores are checked before display: if they do not total 1, or the stated class is
            not its highest-scoring one, the numbers are repaired server-side and the box notes that
            it happened.
          </li>
        </ul>
      </section>

      <section className={styles.section}>
        <h2 className={styles.sectionTitle}>Limits worth knowing</h2>
        <ul className={styles.list}>
          <li>
            Model output is probabilistic. Treat the amber band as a queue for human review, not as
            a decision.
          </li>
          <li>
            The match count saturates: it counts up to 50 neighbours above the floor and stops.
          </li>
          <li>
            Uploads are stored in full, along with a thumbnail, so a past verdict can be re-examined.
            Only you can fetch your own originals.
          </li>
          <li>
            CLIP similarity is semantic, not cryptographic. It matches re-encodes and crops, which a
            file hash would miss, but it can also rate two different photos of the same scene highly.
          </li>
          <li>
            The explanation box needs an API key on the server. Without one it stays switched off and
            says so; the two local checks are unaffected.
          </li>
        </ul>
      </section>
    </div>
  )
}
