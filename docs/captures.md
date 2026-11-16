# Workbench captures

The development-source workbench checks the retained final transient certificate from FiPy’s 400-cell diffusion example: 400 unknowns and 1,920 stored coefficients. The threshold decision concerns component 19 of those stored equations; it does not establish accumulated time-stepping, discretization or physical-model accuracy. FiPy/NIST attribution and terms remain with the example and proof bundle.

The desktop view was captured at 1280 × 800 CSS pixels. The mobile bounds view uses a 390 × 844 CSS-pixel viewport; numeric bounds stay on one line inside a horizontally scrollable table. Both are unmodified captures of the running workbench in an isolated Chrome 157.0.8103.51 session, using current source version 0.2.1.dev0. The original lab.jpg remains a historical capture.

To reproduce, follow the current-source installation and build-site instructions in README.md, choose **FiPy · final transient**, and choose **Check certificate**. Inspect the certified stored-system result and its independent threshold decision. At a narrow width, focus the bounds table and use the right arrow to inspect the remaining columns.

## Capture hashes

- `workbench-0.2.1-dev.png`: `1d7b176b341b1f318aa49cd17200d33f8935d08f4ff775ac574ffb80b5e336c4`
- `bounds-phone-0.2.1-dev.png`: `fb895fca840ee0319c44f339b457e7823ce9d4eb47a4f807237fdb1c0982b263`

## Rendered source hashes

- `web/index.html`: `ca7e1fd83ed47336311fcf7cd85c924fccae856efee623d8c166ca2c1ae86114`
- `web/app.mjs`: `0d604f1fa461320882b232eba907d72a8b5fca0b1e6cd7466cedf8ac92198558`
- `web/style.css`: `9abc6747ed03a5d869eb1f7013fcdefe6562c240de21e573cbaf642f4c8ea566`
- `web/verify.mjs`: `db8a705f77c88794e5f5638b00f88c1444667a8a40e3aa755b629faa0325ef35`
- `web/worker.mjs`: `4049363bbed7959cb38e1f68c3f0fb81ad22c1dc4376f8bce7a0bb4705c6110c`
