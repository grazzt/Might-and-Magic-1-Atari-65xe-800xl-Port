// Validate the installed 6502 language and native decompiler on the C64 bootstrap.
import ghidra.app.script.GhidraScript;
import ghidra.app.decompiler.DecompInterface;
import ghidra.app.decompiler.DecompileResults;
import ghidra.program.model.address.Address;
import ghidra.program.model.listing.Function;
import ghidra.program.model.listing.Instruction;

public class Ghidra6502Smoke extends GhidraScript {
    @Override
    public void run() throws Exception {
        if (!currentProgram.getLanguageID().toString().equals("6502:LE:16:default"))
            throw new Exception("Wrong processor");
        Address entry = toAddr(0x02cb);
        for (var block : currentProgram.getMemory().getBlocks())
            println("MEMORY: " + block.getName() + " " + block.getStart() + " " + block.getEnd() + " size=" + block.getSize());
        if (currentProgram.getMemory().getBlock(entry) == null ||
            currentProgram.getMemory().getBlock(entry).getSize() != 57)
            throw new Exception("Incorrect PRG header handling or payload size");
        if ((getByte(entry) & 0xff) != 0x78)
            throw new Exception("Expected SEI at bootstrap entry");
        disassemble(entry);
        Function function = getFunctionAt(entry);
        if (function == null) function = createFunction(entry, "c64_bootstrap");
        if (function == null) throw new Exception("Could not create bootstrap function");
        analyzeChanges(currentProgram);
        Instruction first = getInstructionAt(entry);
        if (first == null || !first.getMnemonicString().equals("SEI"))
            throw new Exception("6502 decoding failed");
        DecompInterface decompiler = new DecompInterface();
        try {
            if (!decompiler.openProgram(currentProgram))
                throw new Exception("Native decompiler did not open");
            DecompileResults result = decompiler.decompileFunction(function, 30, monitor);
            if (!result.decompileCompleted() || result.getDecompiledFunction() == null)
                throw new Exception("Decompilation failed: " + result.getErrorMessage());
            println(result.getDecompiledFunction().getC());
            println("GHIDRA_6502_SMOKE_PASS: 57-byte bootstrap imported at $02CB, SEI decoded, native decompilation completed.");
        } finally {
            decompiler.dispose();
        }
    }
}
