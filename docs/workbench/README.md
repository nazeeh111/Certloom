# The actual workbench, close enough to read

These are new, unedited native browser element screenshots of Certloom source [`2d256bd2b35f76c2abb97b4b5182a086dd716f1a`](https://github.com/nazeeh111/Certloom/tree/2d256bd2b35f76c2abb97b4b5182a086dd716f1a), captured on 17 November 2026. They show application sections rather than a complete browser viewport. [Open the complete workbench](https://nazeeh111.github.io/Certloom/).

| Capture | Actual browser viewport | Captured section | Native image pixels |
| --- | --- | --- | --- |
| [Desktop decision](decision-wide.png) | 1440 × 1000 | `#decision` | 1464 × 454 |
| [Phone decision](decision-mobile.png) | 320 × 1000 | `#decision` | 516 × 912 |
| [Selected component 399](component-399-mobile.png) | 320 × 1000 | `.component-inspector` | 516 × 672 |

The phone image is the real 258px-wide section rendered at a 320px viewport, with its native type and complete numbers. Native 2× browser capture supplies two image pixels per CSS pixel for readable embedded text; desktop and phone logical widths are 732px and 258px. It is not a reduced desktop dashboard. No raster editing, composition, injected UI state or altered application styling was used. The scientific overview remains separately available in the [retained proof record](../presentation/README.md).

The actual controls selected **FiPy · final transient**, then **Check certificate**. Its retained input has 400 equations and 1,920 stored coefficients. Component 19 is strictly above its stored binary64 0.98 threshold; displayed lower and upper bounds are `0.996898828203779540` and `0.996898828203785027`. The threshold's displayed decimal is rounded upward. Exact fractions, not displayed decimals, determine the result.

For the inspector image, index 399 was entered and **Show** activated using Tab and Space. Its outward-rounded bounds are `0.196192418927731847` and `0.196192418927737335`. That selection does not add a threshold claim for component 399. Expand its disclosure in the actual app to read exact fractions; the full paginated table remains available.

Both actual browser verification downloads matched every result field from the unchanged trusted Python checker. This rechecks the stored equations; it does not rerun the original FiPy solver or establish physical accuracy, accumulated time-stepping accuracy or producer authenticity. The new images do not replace or relabel earlier captures.

[Machine-readable capture provenance](capture-provenance.json) records source/tree identity, original input SHA-256, actions, viewport, section, image dimensions and hashes. The workbench kept its strict security policy and local computation. Required [NIST FiPy terms](../../examples/FIPY-TERMS.txt), [source attribution](../../examples/fipy-provenance.json), [MIT license](../../LICENSE) and [bundled font notices](../../web/fonts/README.md) remain with their original sources.
