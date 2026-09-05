module cache_fsm_tb;

    // Parameters - matching the cache design
    parameter MEM_SIZE        = 1048576;
    parameter CACHE_SIZE      = 1024;
    parameter SETS            = 256;
    parameter ADDRESS_WIDTH   = 32;
    parameter DATA_WIDTH      = 32;
    parameter TAG_WIDTH       = 18;
    parameter SET_WIDTH       = 8;
    parameter OFFSET_WIDTH    = 4;
    parameter WAY             = 4;
    parameter BYTE_OFFSET     = 2;
    parameter WORDS_PER_BLOCK = 16;
    parameter BYTES_PER_WORD  = 4;
    
    parameter CLK_PERIOD = 10;

    // Testbench signals
    logic                              clk;
    logic                              write_en;
    logic                              read_en;
    logic                              reset;
    logic [DATA_WIDTH - 1 : 0]         data_in;
    logic [ADDRESS_WIDTH - 1 : 0]      mem_add;
    logic                              stall;
    logic [DATA_WIDTH - 1 : 0]         data_out;
    logic [3 : 0]                      write_bytes_enable;
    logic [2 : 0]                      load_type;


    // Instantiate the cache FSM
    cache_fsm #(
        .MEM_SIZE(MEM_SIZE),
        .CACHE_SIZE(CACHE_SIZE),
        .SETS(SETS),
        .ADDRESS_WIDTH(ADDRESS_WIDTH),
        .DATA_WIDTH(DATA_WIDTH),
        .TAG_WIDTH(TAG_WIDTH),
        .SET_WIDTH(SET_WIDTH),
        .OFFSET_WIDTH(OFFSET_WIDTH),
        .WAY(WAY),
        .BYTE_OFFSET(BYTE_OFFSET),
        .WORDS_PER_BLOCK(WORDS_PER_BLOCK),
        .BYTES_PER_WORD(BYTES_PER_WORD)
    ) dut (
        .clk(clk),
        .write_en(write_en),
        .read_en(read_en),
        .reset(reset),
        .data_in(data_in),
        .mem_add(mem_add),
        .stall(stall),
        .data_out(data_out),
        .write_bytes_enable(write_bytes_enable),
        .load_type(load_type)
    );

    // Clock generation
    initial begin
        clk = 0;
        forever #(CLK_PERIOD/2) clk = ~clk;
    end

    initial begin
        reset = 1;
        repeat(2)@(posedge clk);
        reset = 0;

        for(integer  i = 0; i < MEM_SIZE; i++) begin
            for (integer j = 0; j < WORDS_PER_BLOCK; j++) begin
                for(integer k = 0; k < BYTES_PER_WORD; k++) begin
                    dut.MAIN_MEMORY[i][j][k] = 0;
                end 
            end
        end

//test 1- write some data and recheck if written properly 
        write_bytes_enable = 4'b1111;
        mem_add = 32'h0000_00F0;
        data_in = 32'hFBFC_FDFE;
        @(posedge clk);
        write_en = 1;
        @(posedge clk);
        write_en = 0;
        repeat(8)@(posedge clk);
//see if the block was correctly loaded from the main memory and read the word
        load_type = 010;
        read_en = 1;
        repeat(3)@(posedge clk);
        read_en = 0;

//test 2- check unsigned byte read after writing at the same tag(for me to check byte offset correctness)
        write_bytes_enable = 4'b0001;
        mem_add = 32'b0000_0000_0000_0000_0000_0000_1111_0011;
        data_in = 32'hFFFF_FFFF;
        @(posedge clk);
        write_en = 1;
        @(posedge clk);
        write_en = 0;
        repeat(8)@(posedge clk);

        load_type = 100;
        read_en = 1;
        repeat(2)@(posedge clk);
        read_en = 0;

//test 3- check sign extend byte access
        load_type = 000;
        read_en   = 1;
        repeat(2)@(posedge clk);
        read_en = 0;



//test 4- fill all ways and test writebacks and read from main memory

        write_bytes_enable = 4'b1111;
        mem_add = 32'h0F00_00F0;
        data_in = 32'hABAB_FDFE;
        @(posedge clk);
        write_en = 1;
        @(posedge clk);
        write_en = 0;
        repeat(8)@(posedge clk);
//see if the block was correctly loaded from the main memory and read the word
        load_type = 010;
        read_en = 1;
        repeat(3)@(posedge clk);
        read_en = 0;

        write_bytes_enable = 4'b1111;
        mem_add = 32'h0D00_00F0;
        data_in = 32'hFBFC_ABAB;
        @(posedge clk);
        write_en = 1;
        @(posedge clk);
        write_en = 0;
        repeat(8)@(posedge clk);
//see if the block was correctly loaded from the main memory and read the word
        load_type = 010;
        read_en = 1;
        repeat(3)@(posedge clk);
        read_en = 0;

        write_bytes_enable = 4'b0011;
        mem_add = 32'h0B00_00F0;
        data_in = 32'hFBAB_ABFE;
        @(posedge clk);
        write_en = 1;
        @(posedge clk);
        write_en = 0;
        repeat(8)@(posedge clk);
//see if the block was correctly loaded from the main memory and read the word
        load_type = 010;
        read_en = 1;
        repeat(3)@(posedge clk);
        read_en = 0;  

//test 5- writeback the lru to the main memory and reread it to check reads from the main memory
//write something new to cause eviction 
        write_bytes_enable = 4'b1111;
        mem_add = 32'h0900_00F0;
        data_in = 32'hDEAD_BEAD;
        @(posedge clk);
        write_en = 1;
        @(posedge clk);
        write_en = 0;
        repeat(8)@(posedge clk);
//see if the block was correctly loaded from the main memory and read the word
        load_type = 010;
        read_en = 1;
        repeat(3)@(posedge clk);
        read_en = 0;   

        mem_add = 32'h0D00_00F0;
        load_type = 010;
        read_en = 1;
        repeat(10)@(posedge clk);  //expect FBFC_ABAB          

        $finish;
    end
endmodule