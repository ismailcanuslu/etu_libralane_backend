`timescale 1ns / 1ps

module tb_counter_10;

    reg        clk;
    reg        rst_n;
    reg        enable;
    wire [3:0] count;
    wire       wrap;

    counter_10 uut (
        .clk    (clk),
        .rst_n  (rst_n),
        .enable (enable),
        .count  (count),
        .wrap   (wrap)
    );

    initial clk = 1'b0;
    always #5 clk = ~clk;

    initial begin
        rst_n  = 1'b0;
        enable = 1'b0;

        #20;
        rst_n = 1'b1;

        #10;
        enable = 1'b1;

        #250;

        enable = 1'b0;
        #30;

        enable = 1'b1;
        #100;

        $display("Simülasyon tamamlandı.");
        $finish;
    end

endmodule
