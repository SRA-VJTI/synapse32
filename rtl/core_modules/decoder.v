`default_nettype none
`include "instr_defines.vh"
module decoder (
    input  wire [31:0] instr,
    output wire [ 4:0] rs2,
    output wire [ 4:0] rs1,
    output wire [31:0] imm,
    output wire [ 4:0] rd,

    output wire rs1_valid,
    output wire rs2_valid,
    output wire rd_valid,

    output wire [6:0] opcode,
    output reg  [5:0] instr_id  // changed from 32-bit one-hot to 6-bit IDIs
);

    wire is_r_instr, is_u_instr, is_s_instr, is_b_instr, is_j_instr, is_i_instr;
    wire [2:0] func3;
    wire [6:0] func7;

    assign opcode = instr[6:0];

    assign is_i_instr = (opcode == 7'b0000011) || (opcode == 7'b0010011) || (opcode == 7'b1100111) ? 1'b1 : 1'b0;
    assign is_u_instr = (opcode == 7'b0010111) || (opcode == 7'b0110111) ? 1'b1 : 1'b0;
    assign is_b_instr = (opcode == 7'b1100011) ? 1'b1 : 1'b0;
    assign is_j_instr = (opcode == 7'b1101111) ? 1'b1 : 1'b0;
    assign is_s_instr = (opcode == 7'b0100011) ? 1'b1 : 1'b0;
    assign is_r_instr = (opcode == 7'b0110011) || (opcode == 7'b0100111) || (opcode == 7'b1010011) ? 1'b1 : 1'b0;

    assign rs2 = (is_r_instr || is_s_instr || is_b_instr) ? instr[24:20] : 5'b0;
    assign rs1 = (is_r_instr || is_s_instr || is_b_instr || is_i_instr) ? instr[19:15] : 5'b0;
    assign rd = (is_r_instr || is_u_instr || is_j_instr || is_i_instr) ? instr[11:7] : 5'b0;

    assign func3 = instr[14:12];
    assign func7 = is_r_instr ? instr[31:25] : 7'b0;

    assign rs1_valid = is_r_instr || is_i_instr || is_s_instr || is_b_instr;
    assign rs2_valid = is_r_instr || is_s_instr || is_b_instr;
    assign rd_valid = is_r_instr || is_u_instr || is_j_instr || is_i_instr;
    
    assign imm = 
        is_i_instr ? { {21{instr[31]}}, instr[30:20] } :
        is_s_instr ? { {21{instr[31]}}, instr[30:25], instr[11:7] } :
        is_b_instr ? { {20{instr[31]}}, instr[7], instr[30:25], instr[11:8], 1'b0 } :
        is_u_instr ? { instr[31:12], 12'b0 } :
        is_j_instr ? { {12{instr[31]}}, instr[19:12], instr[20], instr[30:25], instr[24:21], 1'b0 } :
        32'b0;

    // Instruction ID encoding
    always @(*) begin
        case (opcode)
            7'b0110011: begin  // R-type with M Extensions
                case ({
                    func7, func3
                })
                    {7'h00, 3'h0} : instr_id = INSTR_ADD;
                    {7'h20, 3'h0} : instr_id = INSTR_SUB;
                    {7'h00, 3'h4} : instr_id = INSTR_XOR;
                    {7'h00, 3'h6} : instr_id = INSTR_OR;
                    {7'h00, 3'h7} : instr_id = INSTR_AND;
                    {7'h00, 3'h1} : instr_id = INSTR_SLL;
                    {7'h00, 3'h5} : instr_id = INSTR_SRL;
                    {7'h20, 3'h5} : instr_id = INSTR_SRA;
                    {7'h00, 3'h2} : instr_id = INSTR_SLT;
                    {7'h00, 3'h3} : instr_id = INSTR_SLTU;
                    {7'h01, 3'h0} : instr_id = INSTR_MUL;
                    {7'h01, 3'h1} : instr_id = INSTR_MULH;
                    {7'h01, 3'h2} : instr_id = INSTR_MULHSU;
                    {7'h01, 3'h3} : instr_id = INSTR_MULHU;
                    {7'h01, 3'h4} : instr_id = INSTR_DIV;
                    {7'h01, 3'h5} : instr_id = INSTR_DIVU;
                    {7'h01, 3'h6} : instr_id = INSTR_REM;
                    {7'h01, 3'h7} : instr_id = INSTR_REMU;
                    default:        instr_id = INSTR_INVALID;
                endcase
            end
            7'b0010011: begin  // I-type arithmetic
                case (func3)
                    3'h0: instr_id = INSTR_ADDI;
                    3'h4: instr_id = INSTR_XORI;
                    3'h6: instr_id = INSTR_ORI;
                    3'h7: instr_id = INSTR_ANDI;
                    3'h1: instr_id = (imm[11:5] == 7'h00) ? INSTR_SLLI : INSTR_INVALID;
                    3'h5:
                    instr_id = (imm[11:5] == 7'h00) ? INSTR_SRLI : 
                              (imm[11:5] == 7'h20) ? INSTR_SRAI : INSTR_INVALID;
                    3'h2: instr_id = INSTR_SLTI;
                    3'h3: instr_id = INSTR_SLTIU;
                    default: instr_id = INSTR_INVALID;
                endcase
            end

            7'b0000011: begin  // loads
                case (func3)
                    3'h0: instr_id = INSTR_LB;
                    3'h1: instr_id = INSTR_LH;
                    3'h2: instr_id = INSTR_LW;
                    3'h4: instr_id = INSTR_LBU;
                    3'h5: instr_id = INSTR_LHU;
                    default: instr_id = INSTR_INVALID;
                endcase
            end
            7'b0100011: begin  // stores
                case (func3)
                    3'h0: instr_id = INSTR_SB;
                    3'h1: instr_id = INSTR_SH;
                    3'h2: instr_id = INSTR_SW;
                    default: instr_id = INSTR_INVALID;
                endcase
            end
            7'b1100011: begin  // branches
                case (func3)
                    3'h0: instr_id = INSTR_BEQ;
                    3'h1: instr_id = INSTR_BNE;
                    3'h4: instr_id = INSTR_BLT;
                    3'h5: instr_id = INSTR_BGE;
                    3'h6: instr_id = INSTR_BLTU;
                    3'h7: instr_id = INSTR_BGEU;
                    default: instr_id = INSTR_INVALID;
                endcase
            end
            7'b1101111: instr_id = INSTR_JAL;
            7'b1100111: instr_id = INSTR_JALR;
            7'b0110111: instr_id = INSTR_LUI;
            7'b0010111: instr_id = INSTR_AUIPC;
            default:    instr_id = INSTR_INVALID;
        endcase
        // Log all debug information
        // $display("DEBUG Instruction: %b, ID: %d", instr, instr_id);
        // $display("rs1: %d, rs2: %d, rd: %d, imm: %d", rs1, rs2, rd, imm);
        // $display("opcode: %b, func3: %b, func7: %b", opcode, func3, func7);
    end

endmodule
