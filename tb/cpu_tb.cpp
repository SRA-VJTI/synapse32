#include <verilated.h>
#include <iostream>
#include <Vt2b_riscv_cpu.h>
#include "verilated_vcd_c.h"

using namespace std;

void printbinary(int n, int i)
{
    int k;
    for (i--; i >= 0; i--)
    {
        k = n >> i;
        if (k & 1)
            printf("1");
        else
            printf("0");
    }
    printf("\n");
}

int main(int argc, char **argv)
{
    const std::unique_ptr<VerilatedContext> contextp{new VerilatedContext};
    contextp->traceEverOn(true);
    contextp->commandArgs(argc, argv);
    const std::unique_ptr<Vt2b_riscv_cpu> top{new Vt2b_riscv_cpu{contextp.get(), "t2b_riscv_cpu"}};

    top->clk = 0;
    top->reset = 0;
    VerilatedVcdC* tfp = new VerilatedVcdC;
    top->trace(tfp, 99);
    tfp->open("cpu.vcd");
    while(!contextp->gotFinish()){
        contextp->timeInc(1);
        top->clk = !top->clk;

        top->eval();
        if (contextp->time() > 10000)
        {
            break;
        }
        tfp->dump(contextp->time());
        if((top->DataAdr == 0x2000008) && (top->clk == 1) && (top->MemWrite == 1)){
            cout <<  std::dec << contextp->time();
            cout << ": PC at: " << std::hex << top->ProgramCounter << " DataAdr: " << std::hex << top->DataAdr << " Data: " << top->WriteData << endl;
        }
    }

    top->final();
    tfp->close();

    return 0;
}