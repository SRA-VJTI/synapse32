
Languages like Python, JavaScript, Java, C++, etc are portable and can run on just about any CPU hardware. CPU’s do not execute these languages directly. They execute raw _machine instructions_ that have been encoded into bits as defined by an _instruction set architecture_ (ISA). Popular ISAs include x86, ARM, MIPS, RISC-V, etc.

A _compiler_ does the job of translating a program’s source code into a _binary file_ or _executable_ containing machine instructions for a particular ISA. An operating system (and perhaps a runtime environment) does the job of loading the binary file into memory for execution by the CPU hardware that understands the given ISA.

![](https://courses.edx.org/assets/courseware/v1/b485cd28b5bb3196bde2c6b318754327/asset-v1:LinuxFoundationX+LFD111x+3T2022+type@asset+block/Software_development_and_execution_flow.png)

The binary file is easily interpreted by hardware, but not so easily by a human. The ISA defines a human-readable form of every instruction, as well as the mapping of those human-readable _assembly instructions_ into bits. In addition to producing binary files, compilers can generate _assembly code_. An _assembler_ can compile the assembly code into a binary file. In addition to providing visibility to compiler output, assembly programs can also be written by hand. This is useful for hardware tests and other situations where direct low-level control is needed.

![](https://courses.edx.org/assets/courseware/v1/cbbc122d53215d82fadf219936be8c0b/asset-v1:LinuxFoundationX+LFD111x+3T2022+type@asset+block/assembler.png)

