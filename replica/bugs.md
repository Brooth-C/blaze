# Reproduced refinement issues

| ID | Severity | Reproduction / actual | Expected / fix / evidence |
| --- | --- | --- | --- |
| UI01 | S2 | First chord-strip integration left compact waveform editor at zero height | Bound lower grid row to >=180px and reserve arrangement height; Harmony compact tests pass |
| UI02 | S3 | Automatic measured bars have unknown denominator; transport displayed 4/null and invalid ruler | Display detected beat count without inventing denominator; Harmony transport/position assertions pass |
| UI03 | S3 | Adding dark Studio surfaces left detailed chord drawer white | Inherit semantic graphite roles into drawer and canvas; rendered chord-tools-light.png reviewed |
| QA01 | test race | Retry backend state completed before visible button updated | Wait for state and rendered label in existing Stems test; fresh Stems suite passes |
| QA02 | test race | Seek assertion read old transport text before periodic display update | Wait for the actual 11/1 position; fresh Harmony suite passes |

These fixes are in the current refinement patch. No reproduced open S1/S2 from
the exercised local paths. Native Mac and physical-device gaps remain untested;
this table is not a claim of exhaustive defect absence.
