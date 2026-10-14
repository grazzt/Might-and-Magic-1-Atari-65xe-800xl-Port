; Atari 130XE kernel for Might and Magic I: everything the unchanged C64 game
; code needs from the machine. Design and reasons: docs/ATARI-DESIGN.md.
; Built by port/atari/build.py, which supplies config.inc.
;
; The game runs with the OS and BASIC ROMs switched out, at its C64 addresses.
; Four pieces here and the boot code, each assembled for the place it runs at:
;
;   LOADER  $9D00  where the C64 disk loader was. The game's parameters and
;                  the eight entry points keep their addresses. Holds what
;                  must be visible while the OS ROM is switched in for a disk
;                  transfer.
;   UNDER   $DC00  RAM under the OS ROM: interrupt handlers, key reading.
;   TOP     $FF50  stand-ins for the C64's video, sound and CIA registers,
;                  the KERNAL key entry $FFE4 the game calls, and the vectors.
;   EXT     $6800  in extended bank 0, which ANTIC reads: display lists.
;                  The text font is built at $6400 from the OS ROM's.
;   (boot.s)       loaded by the OS from the boot sectors at $2200; sets all
;                  this up, loads what the C64 title program loads, and enters
;                  the game at its start-up stub ($2000).

        .setcpu "6502"
        .include "config.inc"
        .export test_wait_low, test_wait_high, test_wait_stack_low, test_wait_stack_high

; --- Atari hardware and OS -------------------------------------------------
COLPF0  = $D016
COLPF1  = $D017
COLPF2  = $D018
COLPF3  = $D019
COLBK   = $D01A
AUDF1   = $D200
AUDC1   = $D201
AUDF2   = $D202
AUDC2   = $D203
AUDC3   = $D205
AUDC4   = $D207
AUDCTL  = $D208
STIMER  = $D209
KBCODE  = $D209
IRQEN   = $D20E
SKCTL   = $D20F
SKSTAT  = $D20F
PORTB   = $D301
DMACTL  = $D400
CHACTL  = $D401
DLISTL  = $D402
DLISTH  = $D403
CHBASE  = $D409
WSYNC   = $D40A
NMIEN   = $D40E
NMIRES  = $D40F
NMIST   = $D40F
POKMSK  = $10
SDMCTL  = $022F
SDLSTL  = $0230
COLOR1  = $02C5
COLOR2  = $02C6
COLOR4  = $02C8
CHACT   = $02F3
CHBAS   = $02F4
DDEVIC  = $0300
SIOV    = $E459
ROMFONT = $E000

; PORTB: bit 0 OS ROM, 1 BASIC off, 2-3 bank, 4 CPU sees main, 5 ANTIC sees
; main, 7 self-test off. ANTIC always reads extended bank 0.
.if XE64
PB_GAME = $FE
PB_OS = $FF
.else
PB_GAME   = $D2         ; OS out, CPU on main memory
PB_GAME_EXT = $C2       ; OS out, CPU on the extended bank
PB_OS     = $D3         ; OS in, CPU on main memory
PB_OS_EXT = $C3         ; OS in, CPU on the extended bank
.endif

; --- the game (docs/C64-CODE.md, source/c64/game/symbols.txt) -------------
KEY_COUNT    = $C6      ; KERNAL keyboard buffer count
KEY_BUFFER   = $0277
SHIFT_FLAGS  = $028D
SHIFT_LAST   = $028E
KEY_REPEAT   = $028A    ; bit 7: repeat all keys (the game enables this in GO)
REPEAT_RATE  = $028B    ; original KERNAL inter-repeat counter
REPEAT_DELAY = $028C    ; original game's get_key also writes this counter
IRQ_VECTOR   = $0314
GAME_START   = $2000    ; the start-up stub
KEY_WAIT_RETURN = $0E3F ; return address - 1 of the key wait's JSR to the key reader
PAUSE_RETURN = $C37A    ; the same of the pause routine's JSR ($C378)

DISPLAY_MODE = $0389    ; 0 text, 1 lower bitmap on the whole frame, 2 split
GAME_IRQ     = $C5C5    ; the game's interrupt handler, once it is installed
WANTED_SIDE  = $C54D    ; side the game's disk prompt asks for: 1-3 for B-D
TABLE_BLOCK  = $0296    ; the file table: read whenever the game checks the side

; Extended bank 0, which ANTIC reads:
.if XE64
PICTURE = $D800
FONT = $CC00
source = $F0
dest = $F2
.if !DISKS
buffer = $0100
.endif
.else
PICTURE = $4000         ; 9 KB: the play screen, three rows to a 1 KB block
FONT    = $6400         ; 128 characters in C64 screen-code order
MAPS    = $6C00         ; 16 tables of 256: a C64 bitmap byte to Atari pixels
                        ; $7C00: the EXT2 segment, colour choice
row_reuse = $63D4       ; 25 qualification bytes in unused display padding
cache_hit = $63ED       ; only an exact previous uniform palette-input hit
        .export row_reuse, cache_hit
.endif
COLOR_RAM = $D800       ; where the game writes the C64's colour RAM: RAM here

; ============================================================================
        .segment "LOADER"
; $9D00: block, offset, length, address, as the game sets them.
param_address:  .res 2
param_length:   .res 2
param_offset:   .res 1
param_block:    .res 2
.if DISKS
        rts                     ; $9D07 start the drive code: nothing. Two bytes a call that
zx_offhi: .res 1                ;       does nothing, which nobody reaches, are variables
zx_bits:  .res 1
        jmp set_bank            ; $9D0A set the video bank
        jmp disk_read           ; $9D0D
        jmp disk_write          ; $9D10
        rts                     ; $9D13 set disk ID
raw:      .res 1                ; bit 7: the item is stored as it is
writing:  .res 1                ; bit 7: a write
        rts                     ; $9D16 get disk ID
result:   .res 1                ; what the game gets back: 0, or 8 for a failure
abort_sp: .res 1                ; stack as the call began, to leave from inside a refill
        rts                     ; $9D19 protected read
count:    .res 1                ; scratch, also for the colour code
spare1:   .res 1
        rts                     ; $9D1C reset the drive
spare2:   .res 2
side:   .byte 0                 ; $9D1F  not used: which side is in the drive is the player's business
x_after: .byte $13              ; what the C64 loader leaves in X: its clock-line byte
.else
        jmp do_rts              ; $9D07 start the drive code
        jmp set_bank            ; $9D0A set the video bank
        jmp disk_read           ; $9D0D
        jmp disk_write          ; $9D10
        jmp do_rts              ; $9D13 set disk ID
        jmp do_rts              ; $9D16 get disk ID
        jmp do_rts              ; $9D19 protected read
        jmp do_rts              ; $9D1C reset the drive
side:   .byte 0                 ; $9D1F  side in the drive: 0-3 for A-D
x_after: .byte $13              ; what the C64 loader leaves in X: its clock-line byte
do_rts: rts
.endif
; For the lockstep harness (port/atari/lockstep.py). Kept here, not under the
; OS ROM, so that the harness reads RAM whichever way the ROM is switched.
test_mode:      .byte TEST_MODE ; non-zero: the key wait takes keys from script_key only
script_key:     .byte 0         ; next key for the key wait, 0 for none
waiting:        .byte 0         ; non-zero while the key wait is held for script_key
idle:           .byte 0         ; set whenever the game asks for a key and none is there
pause_key:      .byte 0         ; non-zero: the key every pause gets on its first poll

; The C64 loader keeps the two bank bits for its bus traffic and derives the
; byte it later returns in X from them.
set_bank:
        and #$03
        ora #$10
        sta x_after
        rts

.if DISKS
; ---- Four disks, only this disk's items on each -------------------------------
; Format and reasons: docs/DISKS.md. A disk holds the items of one side of the
; C64 game (files, monster pictures, the monster records, the file table), most
; of them compressed with ZX02, and at its end an index: two bytes for every
; block number, naming the item that starts there. Bits 0-10 are its first
; sector, bit 15 is set for an item stored as it is (the roster, which the game
; writes; the monster records and the file table; anything loaded where the OS
; ROM is). A call, in the C64 loader's terms (block, length, address; the offset
; is 0 at every call in the game), reads the index sector, finds the item and
; unpacks it a sector at a time through a 128-byte buffer in the stack page: at
; every call of the game its stack pointer is $F0 or more. Which disk is in the
; drive is the player's business: the game's own file-table check and its
; INSERT DISK prompt see to it; a read that fails, or a block this disk lacks,
; returns a failure and the game asks again. The decoder is Daniel Serpell's
; zx02-optim (MIT licence), as adapted for the Atari Wizardry port: bounded and
; fed a sector at a time.
lz_dst  = $FC           ; output pointer (the game's loader scratch $FC-$FF)
zx_ptr  = $FE           ; match source; its low byte holds the inverted offset - 1
buffer  = $0100         ; $0100-$017F
STACK_LIMIT = $D0       ; the stack pointer must be at least this to read

lz_left:  .res 2        ; output bytes still wanted
saved_irq: .res 2

; Write: whole sectors from memory below the OS ROM, into a stored item (the
; roster: 18 sectors from $6000).
disk_write:
        lda #$80
        bne transfer
disk_read:
        lda #0
transfer:
        sta writing             ; (the index is always read, whatever the call: dcb says read)
        php
        .if XE64
        ldx #0
        stx DMACTL
        .else
        ldx #$22                ; the play screen's interrupts stop while the
        lda shown_mode          ; OS is in: blank it for the transfer. Text
        beq :+                  ; screens stay on.
        ldx #0
        stx DMACTL
:       .endif
        stx SDMCTL
        lda #0
        sta result
        tsx
        stx abort_sp
        cpx #STACK_LIMIT        ; the buffer is in the stack page: not if the stack is deep
        bcs :+
        jmp fail
:
        lda param_address
        sta lz_dst
        lda param_address+1
        sta lz_dst+1
        lda param_length
        sta lz_left
        lda param_length+1
        sta lz_left+1
        ora lz_left
        bne :+
        jmp read_done           ; nothing wanted, nothing to do
:
        lda param_block         ; the index sector: block / 64 from the index's start
        sta count
        lda param_block+1
        asl count
        rol a
        asl count
        rol a
        clc
        adc #<INDEX_SECTOR
        sta sector
        lda #>INDEX_SECTOR
        adc #0
        sta sector+1
        jsr sio_buffer
        lda param_block         ; its entry: two bytes, number block & 63
        asl a
        and #$7E
        tax
        lda buffer,x
        sta sector
        lda buffer+1,x
        sta raw
        and #$07
        sta sector+1
        ora sector
        beq fail                ; this disk has no such block
        lda writing
        bmi write_item
        jsr lz_fill             ; the first sector
        bit raw
        bpl packed
stored: jsr lz_next
        jsr lz_put
        bne stored
        beq read_done
write_item:
        bit raw                 ; only a stored item can be written
        bpl fail
        lda #'P'                ; put sector, no verify; data goes out
        sta dcb+2
        lda #$80
        sta dcb+3
        lda lz_left             ; sectors: length / 128
        asl a
        lda lz_left+1
        rol a
        beq read_done
        sta count
wnext:  lda lz_dst
        ldx lz_dst+1
        jsr read_sector         ; (a put, as dcb says)
        lda lz_dst
        eor #$80
        sta lz_dst
        bmi :+
        inc lz_dst+1
:       inc sector
        bne :+
        inc sector+1
:       dec count
        bne wnext
        beq read_done
fail:   lda #8
        sta result
        bne read_done
packed: jsr lz_decode
read_done:
        lda #'R'                ; the next call starts with its index read
        sta dcb+2
        lda #$40
        sta dcb+3
        jsr game_mode           ; finish a run of sector transfers before returning
        lda param_address       ; leave $FC-$FF and the registers as the C64 loader does
        sta $FC
        clc
        lda param_address+1
        adc param_length+1
        sta $FD
        lda #0
        sta $FE
        sta $FF
        .if XE64
        lda #0
        .else
        lda #$22
        .endif
        sta SDMCTL
        sta DMACTL
        plp
        ldy param_length
        ldx x_after
        lda result
        cmp #0                  ; status 0: Z and carry set
        rts

; The sector in `sector` into the buffer.
sio_buffer:
        lda #<buffer
        ldx #>buffer
        jmp read_sector

; The next byte of the item in A. Keeps X, Y and the carry. The operand of the
; LDA is the position in the buffer, $00-$7F.
lz_next:
lz_at := * + 1
        lda buffer
        inc lz_at
        bmi lz_fill             ; the buffer is done: the next sector (and back)
        rts
; The next sector into the buffer, A, X, Y and the carry kept.
lz_fill:
        php
        pha
        txa
        pha
        tya
        pha
        jsr sio_buffer
        inc sector
        bne :+
        inc sector+1
:       lda #<buffer
        sta lz_at
        pla
        tay
        pla
        tax
        pla
        plp
        rts

; Emit A; Z set when the whole output is there. Keeps X and the carry.
lz_put:
        ldy #0
        sta (lz_dst),y
        inc lz_dst
        bne @count
        inc lz_dst+1
@count: lda lz_left
        bne @low
        dec lz_left+1
@low:   dec lz_left
        lda lz_left
        ora lz_left+1
        rts

lz_decode:
        lda #0
        sta zx_offhi
        lda #$FF
        sta zx_ptr
        lda #$80
        sta zx_bits
        ldx #0
zx_literal:
        inx
        jsr zx_elias
@copy:  jsr lz_next
        jsr lz_put
        beq zx_done
        dex
        bne @copy
        asl zx_bits
        bcs zx_offset
        inx
        jsr zx_elias
zx_match:
        lda lz_dst+1
        sbc zx_offhi            ; C=0 from Elias: subtract the extra byte
        sta zx_ptr+1
@copy:  ldy lz_dst
        lda (zx_ptr),y
        jsr lz_put
        beq zx_done
        lda lz_dst
        bne @same
        inc zx_ptr+1
@same:  dex
        bne @copy
        asl zx_bits
        bcc zx_literal
zx_offset:
        inx
        jsr zx_elias
        beq zx_early_end
        dex
        txa
        lsr a
        sta zx_offhi
        jsr lz_next             ; keeps the carry from the LSR
        ror a
        eor #$FF
        sta zx_ptr
        ldx #1
        jsr zx_skip
        inx
        bcc zx_match
zx_early_end:
        lda #8                  ; the stream ended before the length asked for
        sta result
zx_done:
        rts
zx_data_bit:
        asl zx_bits
        rol a
        tax
zx_elias:
        asl zx_bits
        bne zx_skip
        jsr lz_next             ; keeps the carry: the sentinel bit shifted out
        rol a
        sta zx_bits
zx_skip:
        txa
        bcs zx_data_bit
        rts
.else
; First sector of each side: boot sectors, then four sides of 664 blocks, two
; 128-byte sectors to a block. "Side" 4 is the memory image the boot code
; loads (build.py).
side_low:   .lobytes SIDE0, SIDE0 + 1328, SIDE0 + 2656, SIDE0 + 3984, SIDE0 + 5312
side_high:  .hibytes SIDE0, SIDE0 + 1328, SIDE0 + 2656, SIDE0 + 3984, SIDE0 + 5312

remain: .res 2
skip:   .res 1                  ; bytes to pass over in the first sector
count:  .res 1
status: .res 1
saved_irq: .res 2

; Write: only whole sectors from memory below the OS ROM, which is all the
; game asks for (the roster: 18 sectors from $6000). The loop below then takes
; its direct path for every sector.
disk_write:
        lda #'P'                ; put sector, no verify
        ldx #$80                ; data goes out
        bne transfer
disk_read:
        lda #'R'
        ldx #$40                ; data comes in
transfer:
        sta dcb+2
        stx dcb+3
        php
        lda test_mode           ; in play nobody swaps disks: when the game reads
        bne :+                  ; a side's file table, give it the side it wants
        lda param_block
        cmp #<TABLE_BLOCK
        bne :+
        lda param_block+1
        cmp #>TABLE_BLOCK
        bne :+
        lda WANTED_SIDE
        sta side
:       .if XE64
        ldx #0
        stx DMACTL
        .else
        ldx #$22                ; the play screen's interrupts stop while the
        lda shown_mode          ; OS is in: blank it for the transfer. Text
        beq :+                  ; screens stay on.
        ldx #0
        stx DMACTL
:       .endif
        stx SDMCTL
        lda param_address
        sta target
        lda param_address+1
        sta target+1
        lda param_length
        sta remain
        lda param_length+1
        sta remain+1
        lda param_block         ; sector = side start + block * 2 + offset / 128
        asl a
        sta sector
        lda param_block+1
        rol a
        sta sector+1
        lda param_offset
        bpl :+
        inc sector
:       and #$7F
        sta skip
        ldx side
        clc
        lda sector
        adc side_low,x
        sta sector
        lda sector+1
        adc side_high,x
        sta sector+1
read_next:
        lda remain
        ora remain+1
        bne :+
        jmp read_done
:
        lda skip                ; a whole sector, wanted whole, below the OS ROM?
        bne read_bounce
        lda remain+1
        bne :+
        lda remain
        bpl read_bounce             ; fewer than 128 bytes left
:       lda target+1
        cmp #$BF
        bcs read_bounce
        lda target
        ldx target+1
        jsr read_sector         ; straight to where the game wants it
        lda #128
        bne read_advance
read_bounce:
        lda #<buffer
        ldx #>buffer
        jsr read_sector
        jsr game_mode           ; a partial/upper-RAM copy needs the game bank
        sec                     ; count = min(128 - skip, remain)
        lda #128
        sbc skip
        ldx remain+1
        bne :+
        cmp remain
        bcc :+
        lda remain
:       sta count
        ldx skip
        ldy #0
read_copy:  lda buffer,x
target := * + 1             ; a label, so that build.py finds it
        sta $FFFF,y
        inx
        iny
        cpy count
        bne read_copy
        lda #0
        sta skip
        lda count
read_advance:
        sta count               ; target += A; remain -= A
        clc
        adc target
        sta target
        bcc :+
        inc target+1
:       sec
        lda remain
        sbc count
        sta remain
        bcs :+
        dec remain+1
:       inc sector
        bne :+
        inc sector+1
:       jmp read_next
read_done:
        jsr game_mode           ; finish a run of direct transfers before returning
        lda param_address       ; leave $FC-$FF and the registers as the C64 loader does
        sta $FC
        clc
        lda param_address+1
        adc param_length+1
        sta $FD
        lda #0
        sta $FE
        sta $FF
        .if XE64
        lda #0
        .else
        lda #$22
        .endif
        sta SDMCTL
        sta DMACTL
        plp
        ldy param_length
        ldx x_after
        lda #0
        cmp #0                  ; status 0: Z and carry set
        rts

.endif
; Read one sector to the address in A (low), X (high). The OS ROM does the
; transfer; it gets its own zero page and interrupt handlers for the duration.
; Consecutive direct sectors keep the OS in until a bounce copy or read_done.
read_sector:
        sta buffer_address
        stx buffer_address+1
        lda PORTB
        lsr a
        bcs @os_ready
        lda IRQ_VECTOR          ; the OS's serial code uses this as a temporary
        sta saved_irq
        lda IRQ_VECTOR+1
        sta saved_irq+1
        sei
        lda #0
        sta NMIEN
        sta AUDC1               ; SIO owns POKEY until the OS is switched out
        sta AUDC2
        jsr swap_zero_page      ; while the save area under the ROM is still visible
        lda #PB_OS
        sta PORTB
        lda POKMSK
        sta IRQEN
        lda #$40
        sta NMIEN
        cli
@os_ready:
        ldx #11
:       lda dcb,x
        sta DDEVIC,x
        dex
        bpl :-
        jsr SIOV
.if DISKS
        cpy #1                  ; any failure ends the call: the game asks again
        beq :+
        ldx abort_sp
        txs
        jmp fail
:       rts
.else
        sty status
        rts
.endif
game_mode:
        lda PORTB
        lsr a
        bcc @done
        sei
        lda #0
        sta NMIEN
        sta IRQEN
        lda #PB_GAME
        sta PORTB
        jsr swap_zero_page
        jsr sound_restore       ; restore clocks, keyboard scanning and the note cache
        lda saved_irq
        sta IRQ_VECTOR
        lda saved_irq+1
        sta IRQ_VECTOR+1
        lda #$40
        sta NMIEN
@done:
        rts                     ; interrupts stay masked until the caller's PLP

; Last step of the boot: the boot code has set the parameters for the piece of
; memory it occupies itself. Load it, then enter the game with the registers
; the C64 has at this point.
.if (!DISKS) .and (!XE64)
enter_game:
        jsr disk_read
        lda #0
        sta side
        ldx #START_S
        txs
        lda #START_P
        pha
        lda #START_A
        ldx #START_X
        ldy #START_Y
        plp
        jmp GAME_START
.endif

swap_zero_page:
        ldx #$7F
:       lda $00,x
        ldy zp_save,x
        sta zp_save,x
        sty $00,x
        dex
        bpl :-
        rts

dcb:    .byte $31, 1, 'R', $40  ; disk 1, read, data comes in
buffer_address: .word buffer
        .byte 7, 0              ; timeout
        .word 128
sector: .word 0                 ; sector, shared with the loop (copied with the DCB)

; Native tests run their one-shot trampoline here while SIO is idle. Each
; buffered disk read replaces all 128 bytes before using them.
.if DISKS .or XE64
probe_scratch = buffer          ; (the stack page; the stack is far above while SIO is idle)
.else
probe_scratch:
buffer: .res 128
.endif

; Generated from the original effect data; stays visible whichever bank ANTIC
; or the CPU is reading. No additional game operand is redirected for sound.
        .if !XE64
        .include "sound-pitches.inc"
        .endif
sound_pitches_end:
        .if XE64
        .include "font65.s"
        .endif

; ============================================================================
        .segment "UNDER"
zp_save:        .res 128        ; the OS's zero page while the game has its own
last_code:      .byte $FF

.if XE64
shown_mode:     .byte $FF
.else
shown_mode:     .byte 0         ; display mode of the picture ANTIC is showing; 0: text
.endif
.if XE64
frame_ready:    .byte 0
.else
frame_ready:    .byte 1         ; zero while a mode change overwrites PICTURE
.endif
frames:         .byte 0         ; counts vertical blanks
stamp:          .byte 0         ; frames at the last call for a key
key_given:      .byte 0         ; a key was returned since the picture was last copied
dli_row:        .byte 0

; Display-list interrupt at the end of every row of the play screen: character
; set and colours for the next row. Very little may come before WSYNC: ANTIC
; takes about 40 of the line's 114 cycles (docs/ATARI-DESIGN.md).
nmi:    bit NMIST
        bvs vbi                 ; a vertical blank is pending: it comes first
        pha
        txa
        pha
        ldx dli_row
        lda row_chbase,x
        sta WSYNC
        sta CHBASE
        .if !XE64
        lda row_pf0,x
        sta COLPF0
        lda row_pf1,x
        sta COLPF1
        lda row_pf2,x
        sta COLPF2
        lda row_pf3,x
        sta COLPF3
        .endif
        inc dli_row
        sta NMIRES
        pla
        tax
        pla
        rti

; Vertical blank. The stack is left as the C64 KERNAL leaves it before it
; jumps through $0314, because the game's own handler ends by chaining to the
; address it found there, and that is irq_tail.
vbi:    pha
        txa
        pha
        tya
        pha
        sta NMIRES
        inc frames
        lda shown_mode
        beq @text
        lda #<bitmap_list
        sta DLISTL
        lda #>bitmap_list
        sta DLISTH
        lda row_chbase
        sta CHBASE
        .if XE64
        lda #PF0_65
        sta COLPF0
        lda #PF1_65
        sta COLPF1
        lda #$0E
        sta COLPF2
        sta COLPF3
        .else
        lda row_pf0
        sta COLPF0
        lda row_pf1
        sta COLPF1
        lda row_pf2
        sta COLPF2
        lda row_pf3
        sta COLPF3
        .endif
        lda #1
        sta dli_row
        lda #$C0
        bne @set
@text:  lda #<text_list
        sta DLISTL
        lda #>text_list
        sta DLISTH
        lda #>FONT
        sta CHBASE
        lda #0                  ; background, then text brightness: the OS's
        sta COLPF2              ; order. Either order shows the same (tried
        lda #$0E                ; 2026-10-11; PORTING-LOG entry 18).
        sta COLPF1
        lda #$40
@set:   .if XE64
        ldx frame_ready
        bne :+
        lda #$40
:       .endif
        sta NMIEN
        lda frame_ready
        beq :+
        lda #$22
:       sta DMACTL
        lda #0
        sta COLBK
        tsx
        lda $0104,x             ; flags of the interrupted code
        and #$04
        bne leave               ; it had interrupts masked; a C64 would wait
        jsr keyboard
        jmp (IRQ_VECTOR)

; What the KERNAL's handler at $EA31 does that the game depends on: the clock.
irq_tail:
        .if XE64
        lda frame_ready
        and #1                  ; bit 7 means a visible frame is being updated
        .else
        jsr sound_update        ; after the game's IRQ has written fake_sid
        lda PORTB               ; bitmap conversion holds the original program
        and #$10                ; its equality-based pauses must not lose ticks
        .endif
        beq leave               ; presentation busy: hold the KERNAL clock
        inc $A2
        bne leave
        inc $A1
        bne leave
        inc $A0
leave:  pla
        tay
        pla
        tax
        pla
irq:    rti

; The KERNAL's GETIN: next key from the buffer in A, 0 if none. In test mode
; a call from the key-wait loop instead holds until the harness supplies a
; key, so that every key arrives on the loop's first pass, and a call from the
; pause routine finds pause_key in the buffer if the harness has set one
; (docs/ORACLE.md, the timing rules).
getin:  sec                     ; the game is asking for a key: the moment to
        lda frames              ; show what it has drawn. Copy the picture when
        sbc stamp               ; this is the first call for a while (a new wait
        cmp #2                  ; or pause) or a key has been taken since.
        bcs :+
        lda key_given
        beq :++
:       .if XE64
        jsr refresh
        .else
        lda #PB_GAME_EXT
        sta PORTB
        jsr refresh
        lda #PB_GAME
        sta PORTB
        .endif
        lda #0
        sta key_given
:       lda frames
        sta stamp
        lda test_mode
        beq getin_buffer
        tsx
        lda $0103,x
        cmp #<PAUSE_RETURN
        bne getin_wait
        lda $0104,x
        cmp #>PAUSE_RETURN
        bne getin_wait
        lda pause_key
        beq getin_buffer
        sta KEY_BUFFER
        lda #1
        sta KEY_COUNT
        bne getin_buffer
getin_wait:
test_wait_stack_low = * + 1
        lda $0103,x
test_wait_low = * + 1            ; harness may select a direct GETIN caller
        cmp #<KEY_WAIT_RETURN
        bne getin_buffer
test_wait_stack_high = * + 1
        lda $0104,x
test_wait_high = * + 1
        cmp #>KEY_WAIT_RETURN
        bne getin_buffer
        lda #1
        sta waiting
:       lda script_key
        beq :-
        ldx #0
        stx script_key
        stx waiting
        inc key_given
        rts
getin_buffer:
        lda KEY_COUNT
        beq getin_none
        ldy KEY_BUFFER
        ldx #0
:       lda KEY_BUFFER+1,x
        sta KEY_BUFFER,x
        inx
        cpx #9
        bne :-
        dec KEY_COUNT
        inc key_given
        tya
        rts
getin_none:  inc idle
        lda #0
        rts

; Once a frame: new keys and enabled held-key repeats enter the C64 buffer.
; Keep the KERNAL delay/rate counters that the original game controls.
keyboard:
        lda SKSTAT
        and #$04
        beq @down
        lda #$FF
        sta last_code
        rts
@down:  lda KBCODE
        cmp last_code
        bne @new
        bit KEY_REPEAT
        bpl @done               ; all-key repeat remains under the game's control
        lda REPEAT_DELAY
        beq @rate
        dec REPEAT_DELAY
        bne @done
@rate:  dec REPEAT_RATE
        bne @done
        lda #4                  ; same four scans between repeats as the KERNAL
        sta REPEAT_RATE
        lda KEY_COUNT
        bne @done               ; repeat only into an empty buffer, no backlog
        beq @translate
@new:
        sta last_code
        lda #$10                ; the game's reader may extend this to $30
        sta REPEAT_DELAY
@translate:
        lda last_code
        and #$3F
        tax
        lda key_table,x
        beq @done
        ldy #0
        bit last_code           ; bit 7 CTRL, bit 6 SHIFT
        bpl :+
        and #$1F                ; CTRL-A is 1, as on the C64
        ldy #4
:       sty SHIFT_FLAGS
        sty SHIFT_LAST
        ldx KEY_COUNT
        cpx #10
        bcs @done
        sta KEY_BUFFER,x
        inc KEY_COUNT
@done:  rts

; One SID voice translated to joined POKEY channels 1+2. The original game
; still owns sequencing, duration, sound enable and interruption by keys.
; Called from the VBI tail, never from the time-sensitive row DLI. Uses no ZP.
sound_restore:
        lda #$50                ; fast clock, channels 1+2 linked: period = N+7
        sta AUDCTL
        lda #3
        sta SKCTL               ; leave keyboard scanning enabled after SIO
        lda #0
        sta AUDC1
        sta AUDC2
        sta AUDC3
        sta AUDC4
        .if !XE64
        lda #$FF                ; SIO may have changed the divisor registers
        sta sound_note
        .endif
        rts
.if !XE64
sound_mute:
        lda #0
        sta AUDC2
        sta sound_level
        sta sound_gate
        sta sound_phase
        rts
sound_update:
        cld                     ; the interrupted game's decimal flag is restored by RTI
        lda $03A0               ; effect stopped, including a key-induced stop
        beq sound_mute
        lda $03A1               ; user's sound-off option
        bne sound_mute
        lda fake_sid+$18
        and #$0F
        beq sound_mute
        sta sound_master
        lda fake_sid+4
        and #$70                ; triangle, saw or pulse waveform present
        beq sound_mute
        ldx #SOUND_NOTES-1
@pitch: lda fake_sid
        cmp sound_freq_low,x
        bne @next
        lda fake_sid+1
        cmp sound_freq_high,x
        beq @found
@next: dex
        bpl @pitch
        bmi sound_mute          ; unrecognised pitch: fail silent instead of a stale note
@found: cpx sound_note
        beq @gate
        stx sound_note
        lda sound_div_low,x
        sta AUDF1
        lda sound_div_high,x
        sta AUDF2
        sta STIMER              ; restart only when changing pitch or after SIO
@gate: lda fake_sid+4
        and #1
        cmp sound_gate
        beq @advance
        sta sound_gate
        sta sound_phase         ; rising gate attacks; falling gate releases
@advance:
        lda sound_phase
        cmp #1
        bne @fall
        lda fake_sid+5
        lsr a
        lsr a
        lsr a
        lsr a
        tax
        lda sound_level
        clc
        adc sound_attack_step,x
        bcs @peak
        cmp #$F0
        bcc @store
@peak: lda #2
        sta sound_phase
        lda #$F0
        bne @store
@fall: ldy #0                   ; release target is zero
        lda fake_sid+6
        ldx sound_phase
        beq @rate               ; release speed comes from sustain/release
        and #$F0
        tay                     ; decay target is the sustain level
        lda fake_sid+5          ; decay speed comes from attack/decay
@rate: sty sound_target
        and #$0F
        tax
        lda sound_level
        sec
        sbc sound_release_step,x
        bcc @target
        cmp sound_target
        bcs @store
@target:
        lda sound_target
@store: sta sound_level
        lsr a
        lsr a
        lsr a
        lsr a
        cmp sound_master
        bcc @volume
        lda sound_master
@volume:
        ora #$A0                ; POKEY pure square tone; channel 1 is silent
        sta AUDC2
        rts

; POKEY key code (0-63) to PETSCII; 0 for keys the game has no use for.
; ESC gives $5F, the C64's left arrow, which is the game's Escape.
.endif
key_table:
        .byte 'L', 'J', ';', 0, 0, 'K', '+', '*'        ; $00
        .byte 'O', 0, 'P', 'U', $0D, 'I', '-', '='      ; $08
        .byte 'V', 0, 'C', 0, 0, 'B', 'X', 'Z'          ; $10
        .byte '4', 0, '3', '6', $5F, '5', '2', '1'      ; $18
        .byte ',', ' ', '.', 'N', 0, 'M', '/', 0        ; $20
        .byte 'R', 0, 'E', 'Y', 0, 'T', 'W', 'Q'        ; $28
        .byte '9', 0, '0', '7', $14, '8', '<', '>'      ; $30
        .byte 'F', 'H', 'D', 0, 0, 'G', 'S', 'A'        ; $38

; Per row of the play screen: the 1 KB block its cells are in, and its three
; colours. Rows 0-15 are the view and the command panel, the rest is text.
.if XE64
        .include "display65.s"
.else
row_chbase:
        .repeat 25, row
        .byte >(PICTURE + (row / 3) * $400)
        .endrepeat
; The colours are chosen for every row by the screen copy (choose_colours).
row_pf0:        .res 25, $04
row_pf1:        .res 25, $08
row_pf2:        .res 25, $0E
row_pf3:        .res 25, $BE    ; pair 11 in the panel's columns
; Palette scratch is never used with the OS ROM enabled.
used_ram:       .res 16
mapping_chosen: .byte $FF,$FF,$FF ; key for the live pair/pair4 mapping; cold invalid
row:            .res 1
cells:          .res 1

.endif
; ============================================================================
        .segment "TOP"
fake_vic:
.if XE64
; The complete game inventory uses only VIC offsets $11-$21. Reuse the
; unused low registers for flip completion and the high registers for CHBASE.
mode_resume:
        lda frames
:       cmp frames
        beq :-                  ; publish before the game clears its old page
        pla
        tay
        pla
        tax
        pla
        plp
        cli                     ; same interrupt state as the original mode entry
        rts
mode_resume_end:
        .res $11 - (* - fake_vic)
        .res $11
row_chbase: .res 25
        .res 64 - (* - fake_vic)
.else
        .res 64
.endif         ; $D000-$D03F as the game's code sees it
fake_sid:       .res 32         ; $D400-$D41F
; The three CIA registers the game's code names: $DC0D, $DD00, $DD02 (build.py,
; CIA_REGISTERS). Their own addresses are the UNDER segment here, so a store
; to one would land in the kernel. What the game reads back does not matter:
; only the two bank bits it adds reach set_bank.
fake_cia:       .res 3
.if XE64
text_list:
        .byte $70, $70, $42
        .word PICTURE
        .res 24, $02
        .byte $41
        .word text_list
rom_high:
        .byte $E3,$E3,$E0,$E0,$E1,$E1,$E2,$E2
rom_high_end:
mode:           .res 1
font_half:      .res 1
font_failed:    .byte 0
font_stack_min: .byte $FF
        .res $FFE4 - $FF50 - (* - fake_vic)
        jmp getin
sound_state_end:
rf_blank:
        lda #0
        sta frame_ready
        sta DMACTL
        lda #$40
        sta NMIEN
        rts
        .res $FFFA - $FF50 - (* - fake_vic)
        .word nmi, nmi, irq
.else
        .include "sound-envelope.inc"
sound_envelope_end:
idempotent:                     ; converter qualification; visible with OS out
        .byte 1,1,0,1,0,1,0,0,1,1,1,1,1,1,0,1
idempotent_end:
        .res $FFE4 - $FFB3 - (idempotent_end - sound_attack_step) ; free
        jmp getin               ; $FFE4: KERNAL GETIN
; Volatile envelope state occupies previously unused bytes above GETIN.
; This frees room in UNDER for the clock guard during bitmap conversion.
sound_note:     .byte $FF
sound_gate:     .byte 0
sound_phase:    .byte 0         ; 1 attack, 2 decay/sustain, 0 release
sound_level:    .byte 0         ; 0..240; high nibble is POKEY volume
sound_target:   .byte 0
sound_master:   .byte 0
sound_state_end:
rf_blank:                       ; use spare TOP bytes for this small helper
        lda #0
        sta frame_ready
        sta DMACTL
        rts
        .res $FFFA - $FFE7 - 6 - 9 ; free
        .word nmi               ; NMI: only the vertical blank is enabled
        .word nmi
        .word irq               ; IRQ: none is enabled while the OS is out

; ============================================================================
        .segment "EXT"
; Text screens: a completed snapshot. The game reuses $0400 for bitmap
; colours before setting DISPLAY_MODE, so ANTIC must never read it live.
text_list:
        .byte $70, $70          ; 16 blank lines: 25 rows need the room
        .byte $42
        .word PICTURE
        .res 24, $02
        .byte $41
        .word text_list

; The play screen: 25 rows of ANTIC mode 4. Each row's 40 cells are 40
; characters of the 1 KB block the row is in (PICTURE, three rows to a block),
; so the character codes are always the same three rows of numbers. In the
; first 16 rows the panel's columns have bit 7 set, drawing pair 11 in
; register 3. Refresh adjusts columns 22-29 for the wider encounter list.
bitmap_list:
        .byte $70, $70
        .repeat 25, row
        .if row < 24
        .byte $C4               ; mode 4, load address, interrupt
        .else
        .byte $44
        .endif
        .if row < 16
        .word codes_panel + (row .mod 3) * 40
        .else
        .word codes_plain + (row .mod 3) * 40
        .endif
        .endrepeat
        .byte $41
        .word bitmap_list
codes_plain:
        .repeat 120, i
        .byte i
        .endrepeat
codes_panel:
        .repeat 120, i
        .if (i .mod 40) < 30
        .byte i
        .else
        .byte i | $80
        .endif
        .endrepeat

; Where each row of the two C64 bitmaps and their colour matrices is, and
; where it goes in PICTURE.
upper_low:  .repeat 25, row
            .byte <($2000 + row * 320)
            .endrepeat
upper_high: .repeat 25, row
            .byte >($2000 + row * 320)
            .endrepeat
lower_low = upper_low
umatrix_low = cram_low
lmatrix_low = cram_low
umatrix_high: .repeat 25, row
              .byte >($0400 + row * 40)
              .endrepeat
picture_low:  .repeat 25, row
              .byte <(PICTURE + (row / 3) * $400 + (row .mod 3) * 320)
              .endrepeat
picture_high: .repeat 25, row
              .byte >(PICTURE + (row / 3) * $400 + (row .mod 3) * 320)
              .endrepeat
; Exact palette-input caches for rows 6-24. Eight 60-byte records live in
; character-block tails, eleven in the unused last block after its one row.
; Record: 40 matrix bytes, 16 mappings, uniform RAM nibble ($FF varied),
; and three selected C64 colours. Varied rows can still reuse their mappings.
palette_low: .repeat 25, r
             .if r >= 6 && r < 14
             .byte <(PICTURE + (r - 6) * $400 + $3C0)
             .else
             .byte <($6140 + (r - 14) * 60)
             .endif
             .endrepeat
palette_high: .repeat 25, r
             .if r >= 6 && r < 14
             .byte >(PICTURE + (r - 6) * $400 + $3C0)
             .else
             .byte >($6140 + (r - 14) * 60)
             .endif
             .endrepeat

; Copy what the C64 would be showing into PICTURE. The game draws in the
; C64's layout (rows 320 bytes apart) and chooses three colours per cell
; through its colour matrices. An Atari row has three colours for all its
; cells, so each row first gets the three that serve it best (choose_colours),
; and then every byte goes through the table that turns its cell's pixel pairs
; into those. Called with the CPU on this bank. Uses $F0-$F7 and puts them
; back.
source  = $F0
dest    = $F2
matrix  = $F4
cram    = $F6
refresh:
        lda IRQ_VECTOR          ; before the game installs its handler it shows text
        cmp #<GAME_IRQ
        bne rf_text
        lda IRQ_VECTOR+1
        cmp #>GAME_IRQ
        bne rf_text
        lda DISPLAY_MODE
        bne rf_bitmap
rf_text:
        lda shown_mode
        beq :+
        jsr rf_blank
:       ldy #0
:       lda $0400,y
        sta PICTURE,y
        lda $0500,y
        sta PICTURE+$100,y
        lda $0600,y
        sta PICTURE+$200,y
        lda $0700,y
        sta PICTURE+$300,y
        iny
        bne :-
        lda #0
        sta shown_mode
        lda #1                  ; publish only after the complete snapshot
        sta frame_ready
        rts
rf_bitmap:
        sta mode
        lda shown_mode
        bne :+
        jsr rf_blank
:
        jsr update_panel_codes
        ldx #7
:       lda source,x
        sta kept,x
        dex
        bpl :-
        ldx #0
rf_row:   stx row
        lda cram_low,x
        sta cram
        lda umatrix_high,x      ; colour RAM is exactly $D400 above the matrix
        clc
        adc #$D4                ; derive its high byte instead of storing 25
        sta cram+1
        cpx #16                 ; rows 0-15 come from the upper bitmap in split mode
        bcs rf_lower
        lda mode
        cmp #2
        bne rf_lower
        lda upper_low,x
        sta source
        lda upper_high,x
        sta source+1
        lda umatrix_low,x
        sta matrix
        lda umatrix_high,x
        sta matrix+1
        bne rf_both
rf_lower: lda lower_low,x
        sta source
        lda upper_high,x
        ora #$C0
        sta source+1
        lda lmatrix_low,x
        sta matrix
        lda umatrix_high,x
        ora #$C8
        sta matrix+1
rf_both:
        jsr choose_colours
        ldx row
        lda picture_low,x
        sta dest
        lda picture_high,x
        sta dest+1
        jsr reuse_row
        bcc :+
        jmp rf_next_row
:
        lda #40
        sta cells
rf_cell:  ldy #0
        lda (matrix),y          ; table number: the pair for the cell's 01 colour
        tax                     ; keep the raw byte in X instead of the stack
        lsr a
        lsr a
        lsr a
        lsr a
        tay
        lda pair,y
        sta count
        txa
        and #$0F
        tax
        lda pair4,x
        ora count
        clc
        adc #>MAPS
        cmp #>MAPS+9             ; identity mapping: no lookup or operand writes
        bne :+
        jmp rf_identity
:
        cmp table0+1
        beq rf_table_ready
        sta table0+1
        sta table1+1
        sta table2+1
        sta table3+1
rf_table_ready:
        ldy #7
rf_lookup:
        .repeat 4, b
        lda (source),y
        tax
.ident(.sprintf("table%d", b)) = * + 1
        lda MAPS,x
        sta (dest),y
        dey
        .endrepeat
        bpl rf_lookup
rf_advance:
        clc
        lda source
        adc #8
        sta source
        bcc :+
        inc source+1
:       clc
        lda dest
        adc #8
        sta dest
        bcc :+
        inc dest+1
:       inc matrix
        bne :+
        inc matrix+1
:       dec cells
        beq :+
        jmp rf_cell
:
rf_next_row:
        ldx row
        inx
        cpx #25
        beq :+
        jmp rf_row
:
        ldx #7
:       lda kept,x
        sta source,x
        dex
        bpl :-
        lda mode
        sta shown_mode
        lda #1
        sta frame_ready
        rts
        .segment "EXT2"
mode:   .res 1
        .segment "EXT"
kept:   .res 8
cram_low:   .repeat 25, r
            .byte <(COLOR_RAM + r * 40)
            .endrepeat

; The fixed swap table maps 01 <-> 10, preserving 00/11. Thus
; (swap(b) XOR b) AND b marks used 01 bits in $55 and 10 bits in $AA.
; OR over eight lines to count only matrix colours actually drawn per cell.
matrix_usage:
        lda source
        sta dest
        lda source+1
        sta dest+1
        lda #0
        sta cells
mu_cell:
        lda #0
        sta best
        ldy #7
mu_byte:
        lda (dest),y
        beq mu_next             ; blank lines contribute neither matrix pair
        tax
        lda MAPS+$600,x
        eor (dest),y
        and (dest),y
        ora best
        sta best
mu_next:
        dey
        bpl mu_byte
        ldy cells
        lda (matrix),y
        pha
        lsr a
        lsr a
        lsr a
        lsr a
        tax
        lda best
        and #$55
        beq :+
        inc used_matrix,x
:       pla
        and #$0F
        tax
        lda best
        and #$AA
        beq :+
        inc used_matrix,x
:       clc
        lda dest
        adc #8
        sta dest
        bcc :+
        inc dest+1
:       inc cells
        lda cells
        cmp #40
        bne mu_cell
        jmp matrix_usage_done

; ============================================================================
        .segment "EXT2"
rf_identity:
        ldy #7
ri_byte:
        .repeat 2
        lda (source),y
        sta (dest),y
        dey
        .endrepeat
        bpl ri_byte
        jmp rf_advance

update_panel_codes:
        jsr panel_layout        ; encounter list: 18 cells, commands: 10
        stx panel_boundary
        sta base                ; high-bit mask for the eight extra panel cells
        ldx #7
upc_cell:
        txa
        clc
        adc #22
        ora base
        sta codes_panel+22,x
        adc #40
        sta codes_panel+62,x
        adc #40
        sta codes_panel+102,x
        dex
        bpl upc_cell
        rts

matrix_usage_done:
        ldx row
        lda palette_low,x
        sta dest
        lda palette_high,x
        sta dest+1
        lda #1
        sta cc_pair_flag        ; skip unfiltered counts in cc_cell
        rts

; EN $2742 paints the first list row blue at $D816, 18 cells wide. Mode 1
; also occurs at ordinary doors; those retain the ten-column command panel.
panel_layout:
        ldx #30
        lda DISPLAY_MODE
        cmp #1
        bne pl_commands
        lda COLOR_RAM+22
        and #$0F
        cmp #14
        bne pl_commands
        ldx #22
        lda #$80
        rts
pl_commands:
        lda #0
        rts

; The old encoded row can be reused only with unchanged palette inputs and
; idempotent lookups. Compare all 320 raw bytes exactly; leave both pointers
; at their original starts on success and failure. Carry signals reuse.
reuse_row:
        lda cache_hit
        beq rr_no
        lda row_reuse,x
        beq rr_no
        inc source+1
        inc dest+1
        ldy #63
rr_tail:
        lda (source),y
        cmp (dest),y
        bne rr_restore
        dey
        bpl rr_tail
        dec source+1
        dec dest+1
        ldy #0
rr_page:
        lda (source),y
        cmp (dest),y
        bne rr_no
        iny
        bne rr_page
        sec
        rts
rr_restore:
        dec source+1
        dec dest+1
rr_no:
        clc
        rts

; Choose the three colours of row `row` and how each C64 colour is drawn in
; it. The C64 gives every cell its own three colours: pixel pair 01 the high
; nibble of the screen-matrix byte, 10 the low nibble, 11 the colour RAM.
;   register 2 (pair 11): the commonest colour-RAM colour of the row's cells
;   registers 0 and 1:    the two commonest other matrix colours; encounter
;                        artwork counts only pairs present in the bitmap
; Every C64 colour then goes to the nearest of black and those three
; (pair, and pair4 = pair * 4). Pair 11 is always drawn as 11. In the first 16
; rows register 3 serves the ten-column command panel or eighteen-column
; encounter list, taking that region's commonest colour-RAM colour.
choose_colours:
        lda #0
        sta cache_hit
        ldx row
        lda panel_boundary
        cmp #22
        bne :+
        cpx #16
        bcs :+
        lda #$FF                ; bitmap usage is not in the old palette cache
        sta cache_uniform
        jmp cc_scan
:
        cpx #6
        bcc cc_scan
        lda palette_low,x
        sta dest
        lda palette_high,x
        sta dest+1
        ldy #39
        lda (cram),y
        and #$0F
        sta cache_uniform
:       lda (cram),y            ; the fast case needs identical RAM colour in
        and #$0F                ; all 40 cells, including the command panel
        cmp cache_uniform
        bne cc_varied
        dey
        bpl :-
        lda shown_mode          ; text snapshots invalidate the reused padding
        beq cc_scan
        ldy #56
        lda (dest),y
        cmp cache_uniform
        bne cc_scan
        ldy #39
:       lda (matrix),y          ; exact comparison, no hashes or collisions
        cmp (dest),y
        bne cc_scan
        dey
        bpl :-
        inc cache_hit           ; a mapping-only restore is NOT an exact hit
cc_restore:
        lda #$FF                ; cached pairs replace the live mapping: invalidate
        sta mapping_chosen      ; its key cheaply; the next rebuild records a key
        ldy #55
        ldx #15
:       lda (dest),y
        sta pair,x
        asl a
        asl a
        sta pair4,x
        dey
        dex
        bpl :-
        rts
cc_varied:
        lda #$FF
        sta cache_uniform
cc_scan:
        lda #0
        sta cc_pair_flag
        ldx #15
:       sta used_matrix,x
        sta used_ram,x
        sta used_panel,x
        dex
        bpl :-
        lda panel_boundary
        cmp #22
        bne :+
        lda row
        cmp #16
        bcs :+
        jsr matrix_usage
:
        ldy #39
cc_cell:
cc_pair_flag = * + 1
        lda #0
        bne cc_ram
        lda (matrix),y
        lsr a
        lsr a
        lsr a
        lsr a
        tax
        inc used_matrix,x
        lda (matrix),y          ; a second read costs less than PHA / PLA
        and #$0F
        tax
        inc used_matrix,x
cc_ram:
        lda (cram),y
        and #$0F
        tax
panel_boundary = * + 1
        .export panel_boundary, cc_pair_flag
        cpy #30                 ; patched from the frame's actual panel layout
        bcc :+
        lda row
        cmp #16
        bcs :+
        inc used_panel,x
        bne :++
:       inc used_ram,x
:       dey
        bpl cc_cell
        ldx #15                 ; the panel's commonest colour-RAM colour
        lda #0
        sta best
        ldy #$FF
:       lda used_panel,x
        cmp best
        bcc :+
        beq :+
        sta best
        txa
        tay
:       dex
        bpl :--
        sty panel
        ldx #15                 ; commonest colour-RAM colour
        lda #0
:       cmp used_ram,x
        bcs :+
        lda used_ram,x
        stx chosen+2
:       dex
        bpl :--
        ldx chosen+2
        lda #0
        sta used_matrix,x
        sta used_matrix         ; black is the background
        ldy #0                  ; the two commonest matrix colours
cc_pick:
        lda chosen+2            ; none left: fall back on the colour-RAM colour
        sta chosen,y
        ldx #15
        lda #0
        sta best
:       lda used_matrix,x
        cmp best
        bcc :+
        beq :+
        sta best
        txa
        sta chosen,y
:       dex
        bpl :--
        ldx chosen,y
        lda #0
        sta used_matrix,x
        iny
        cpy #2
        bne cc_pick
        ldx row
        ldy chosen
        lda atari_colour,y
        sta row_pf0,x
        ldy chosen+1
        lda atari_colour,y
        sta row_pf1,x
        ldy chosen+2
        lda atari_colour,y
        sta row_pf2,x
        ldy panel               ; no panel in this row: as register 2
        bmi :+
        lda atari_colour,y
:       sta row_pf3,x
        cpx #6
        bcc cc_rebuild
        lda shown_mode
        beq cc_rebuild
        ldy #59
        ldx #2
:       lda (dest),y
        cmp chosen,x
        bne cc_rebuild
        dey
        dex
        bpl :-
        jsr cc_restore
        jmp cc_save
cc_rebuild:
        ldx #2                  ; neighbouring rows often choose the same triple
:       lda chosen,x            ; ordered C64 colours, exact comparison
        cmp mapping_chosen,x
        bne cc_new_mapping
        dex
        bpl :-
cc_shared_hit:
        jmp cc_save             ; pair/pair4 already hold precisely this mapping
cc_new_mapping:
        ldx #2
:       lda chosen,x
        sta mapping_chosen,x
        dex
        bpl :-
        ldx #15                 ; each C64 colour to the nearest of the four
cc_near:
        stx base
        lda distance,x          ; the packed table's first row is from black
        sta best
        lda #0
        sta pair,x
        ; Same strict-distance comparison and tie order, without a three-way
        ; loop and its index spill for every one of the 16 colours.
        .repeat 3, c
        lda chosen+c
        jsr colour_distance
        cmp best
        bcs :+
        sta best
        lda #c+1
        sta pair,x
:
        .endrepeat
        lda pair,x
        asl a
        asl a
        sta pair4,x
        dex
        bpl cc_near
cc_save:
        lda row
        cmp #6
        bcc cc_done
        ldy #56
        lda cache_uniform
        sta (dest),y
        ldy #39
:       lda (matrix),y
        sta (dest),y
        dey
        bpl :-
        ldx #15
        ldy #55
:       lda pair,x
        sta (dest),y
        dey
        dex
        bpl :-
        ldy #59
        ldx #2
:       lda chosen,x
        sta (dest),y
        dey
        dex
        bpl :-
        ldx row
        lda #0
        sta row_reuse,x
        lda cache_uniform
        cmp #$FF
        beq cc_done
        jsr qualify_row
cc_done:
        rts

; Qualification belongs to the newly completed cache record. It cannot
; authorize reuse on this miss: cache_hit remains zero until a later hit.
qualify_row:
        ldy #39
qr_cell:
        lda (matrix),y
        pha
        lsr a
        lsr a
        lsr a
        lsr a
        tax
        lda pair,x
        sta count
        pla
        and #$0F
        tax
        lda pair4,x
        ora count
        tax
        lda idempotent,x
        beq qr_done
        dey
        bpl qr_cell
        ldx row
        lda #1
        sta row_reuse,x
qr_done:
        rts
; X/base is the source colour, A the candidate. Preserve X and return the
; original rounded distance; Y/count are scratch during mapping creation.
colour_distance:
        cmp base
        bcc cd_lower
        sta count
        lda distance_base,x
        bcs cd_index
cd_lower:
        tay
        lda distance_base,y
        ldy base
        sty count
cd_index:
        clc
        adc count
        tay
        lda distance,y
        rts
palette_code_end:
        .segment "EXT2"
used_matrix:    .res 16
used_panel:     .res 16
chosen:         .res 3          ; C64 colours for registers 0, 1, 2
panel:          .res 1          ; C64 colour for register 3, or $FF
pair:           .res 16         ; C64 colour -> pixel pair in this row
pair4:          .res 16
base:           .res 1
best:           .res 1
cache_uniform:  .res 1
        .include "colours.inc"  ; atari_colour (16) and distance (16 x 16)

.endif ; 130XE converter / 65XE direct display
