module counter_10 (
    input  wire       clk,
    input  wire       rst_n,
    input  wire       enable,
    output reg  [3:0] count,
    output reg        wrap
);

    always @(posedge clk or negedge rst_n) begin
        if (!rst_n) begin
            count <= 4'd0;
            wrap  <= 1'b0;
        end else if (enable) begin
            if (count == 4'd9) begin
                count <= 4'd0;
                wrap  <= 1'b1;
            end else begin
                count <= count + 4'd1;
                wrap  <= 1'b0;
            end
        end else begin
            wrap <= 1'b0;
        end
    end

endmodule
