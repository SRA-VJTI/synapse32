Waveform viewers have been the standard debug tool for circuit design since dinosaurs roamed the earth. But Makerchip supports a better debug methodology as well. We have prepared some custom visualization to help with the debug of your calculator. As always, check the box for each step when done, to ensure you perform all required steps.

To include this visualization:

- Paste this single line below the "**m4_makerchip_module**" line to include the visualization library:  

 ```
m4_include_lib(['https://raw.githubusercontent.com/stevehoover/LF-Building-a-RISC-V-CPU-Core/main/lib/calc_viz.tlv'])

```
 it may be necessary to correct the single-quote characters by retyping them after cut-and-pasting.

- Add this line as the last line in the **\TLV** region:
```
m4+calc_viz()

```
to instantiate the visualization and then compile it.

- You should now see a calculator in the VIZ pane. If necessary, debug the LOG. In NAV-TLV, the **m4_include_lib** line should have turned into a comment, and the **m4+calc_viz()** macro instantiation should have expanded to a block of "**\viz**" code.

- Lay out your IDE so you can see both VIZ and WAVEFORM. Step through VIZ to see the operations performed by your calculator. Note that your calculator, like the waveform, is showing values in hexadecimal. Relate what you see in VIZ to what you see in the waveform. If you notice incorrect behavior, debug it by isolating the faulty logic and fixing it.
