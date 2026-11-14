# Test data

Real spectra used by the test suite. They are third-party files, not covered by this
project's GPL licence; each set keeps its original MIT licence (see the `LICENSE-*.txt`
file next to the data).

## bruker/

Source: <https://github.com/cheminfo/bruker-data-test> (MIT, © cheminfo), `data/zipped/`.
Each zip holds one Bruker experiment folder; tests unpack it to a temporary directory.

| File | Content |
|---|---|
| `ibuprofen-1h-processed.zip` | ¹H, 600 MHz, FID (32k points) plus TopSpin-processed spectrum (`pdata/1`) |
| `ibuprofen-13c-processed.zip` | ¹³C, 151 MHz, FID (32k points) plus TopSpin-processed spectrum |
| `aspirin-1h.zip` | ¹H, 300 MHz, FID only (8k points) |
| `ibuprofen.mol` | Structure of ibuprofen |

The TopSpin-processed spectra serve as the reference our own processing is compared against.

## jcamp/

Source: <https://github.com/cheminfo/jcamp-data-test> (MIT, © cheminfo), `data/nmr/`.

| File | Content |
|---|---|
| `aspirin-1h.fid.dx` | ¹H FID, Bruker export |
| `aspirin-1h.dx` | ¹H spectrum (real + imaginary), Bruker export |
| `jeol-1h.dx` | ¹H spectrum, JEOL export |
| `varian-1h.jdx` | ¹H spectrum, Varian/Agilent export |
