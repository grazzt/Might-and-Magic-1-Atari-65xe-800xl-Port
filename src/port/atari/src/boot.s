; Boot code for the Atari build: loaded by the OS from the boot sectors, it
; puts the kernel's pieces (kernel.s) in place, loads from side A what the C64
; title program loads, sets the memory the game expects to find as the C64
; left it, and enters the game at its start-up stub. port/atari/build.py
; supplies config.inc, loads.inc, kernel.inc (the kernel's labels) and the
; binary pieces.

        .setcpu "6502"
        .include "config.inc"
        .include "kernel.inc"

IRQEN   = $D20E
SKCTL   = $D20F
PORTB   = $D301
DMACTL  = $D400
CHACTL  = $D401
DLISTL  = $D402
CHBASE  = $D409
NMIEN   = $D40E
COLPF1  = $D017
COLPF2  = $D018
COLBK   = $D01A
SDMCTL  = $022F
SDLSTL  = $0230
COLOR1  = $02C5
COLOR2  = $02C6
COLOR4  = $02C8
CHACT   = $02F3
CHBAS   = $02F4
ROMFONT = $E000
IRQ_VECTOR = $0314
GAME_START = $2000
.if XE64
PB_GAME = $FE
PB_OS = $FF
FONT = $CC00
.else
PB_GAME   = $D2
PB_OS     = $D3
PB_OS_EXT = $C3
PB_GAME_EXT = $C2
MAPS    = $6C00
FONT    = $6400
.endif

        .segment "BOOT"
        .byte 0                 ; boot flags
        .byte BOOT_SECTORS
        .word BOOT_LOAD
        .word boot              ; DOSINI; not used, boot never returns

boot:   lda #PB_OS
        sta PORTB
        ldy #0                  ; the pieces that live below the OS ROM
:       lda image_loader,y
        sta $9D00,y
        lda image_loader+$100,y
        sta $9E00,y
        lda image_loader+$200,y
        sta $9F00,y
        iny
        bne :-
        .if !XE64
        lda #PB_OS_EXT          ; CPU on the extended bank, OS ROM still in
        sta PORTB
        ldy #0                  ; text font in C64 screen-code order from the ROM's:
:       lda ROMFONT+$300,y      ; codes $00-$1F: lower case
        sta FONT,y
        lda ROMFONT,y           ; $20-$5F: the same characters as ASCII
        sta FONT+$100,y
        lda ROMFONT+$100,y
        sta FONT+$200,y
        lda ROMFONT+$200,y      ; $60-$7F: graphics characters
        sta FONT+$300,y
        iny
        bne :-
        lda #$20                ; completed text snapshot starts as blank
        ldy #0
:       sta $4000,y
        sta $4100,y
        sta $4200,y
        sta $4300,y
        iny
        bne :-
        ldy #0                  ; display lists, tables and the copy routine
:       lda image_ext,y
        sta text_list,y
        lda image_ext+$100,y
        sta text_list+$100,y
        lda image_ext+$200,y
        sta text_list+$200,y
        lda image_ext+$300,y
        sta text_list+$300,y
        iny
        bne :-
        lda #PB_OS
        sta PORTB
        .endif
        lda #<text_list         ; the OS keeps showing this during disk transfers
        sta SDLSTL
        lda #>text_list
        sta SDLSTL+1
        lda #>FONT
        sta CHBAS
        lda #2
        sta CHACT
        lda #$0E
        sta COLOR1
        lda #0
        sta COLOR2
        sta COLOR4
        .if XE64
        lda #0
        .else
        lda #$22
        .endif
        sta SDMCTL

        sei                     ; from here the machine is the game's
        lda #0
        sta NMIEN
        sta IRQEN
        sta COLPF2              ; the OS will not copy its shadows any more
        sta COLBK
        lda #$0E
        sta COLPF1
        lda #<text_list
        sta DLISTL
        lda #>text_list
        sta DLISTL+1
        lda #>FONT
        sta CHBASE
        lda #2
        sta CHACTL
        .if XE64
        lda #0
        .else
        lda #$22
        .endif
        sta DMACTL
        lda #PB_GAME
        sta PORTB
        ldy #0
:       lda image_under,y
        sta $DC00,y
        lda image_under+$100,y
        sta $DD00,y
        lda image_under+$200,y
        sta $DE00,y
        lda image_under+$300,y
        sta $DF00,y
        iny
        bne :-
        ldy #TOP_SIZE - 1
:       lda image_top,y
        sta fake_vic,y
        dey
        cpy #$FF
        bne :-
        ldx #$7F
:       lda $00,x
        sta zp_save,x
        dex
        bpl :-
        lda #<irq_tail
        sta IRQ_VECTOR
        lda #>irq_tail
        sta IRQ_VECTOR+1
        lda #3
        sta SKCTL
        lda #$40
        sta NMIEN

        .if !XE64
        ldx #7                  ; the colour tables, too big for the boot sectors:
:       lda tables_load,x       ; read them to memory that is still free, then
        sta load_now,x          ; copy them into the extended bank
        dex
        bpl :-
        jsr load
        lda #PB_GAME_EXT
        sta PORTB
        ldx #20                 ; 16 tables and the colour-choice code: 20 pages
        ldy #0
@page:
@from = * + 2
:       lda TABLES_AT,y
@to = * + 2
        sta MAPS,y
        iny
        bne :-
        inc @from
        inc @to
        dex
        bne @page
        lda #PB_GAME
        sta PORTB

.endif
.if TITLE
        ldx #7                  ; the title stage (title.s) runs the C64's title
:       lda title_load,x        ; program and comes back when Escape is pressed
        sta load_now,x
        dex
        bpl :-
        jsr load
        ldx #BOOT_SECTORS / 2   ; the title program draws where this code is:
        ldy #0                  ; park all of it until then
@park:
@here = * + 2
:       lda BOOT_LOAD,y
@there = * + 2
        sta PARK,y
        iny
        bne :-
        inc @here
        inc @there
        dex
        bne @park
        lda #<after_title
        sta TITLE_AT+3
        lda #>after_title
        sta TITLE_AT+4
        jmp TITLE_AT
after_title:
.endif

        ldx #0                  ; what the C64 title program loads from side A, and
@load:  lda load_table,x        ; what else it leaves in memory, from the image
        sta side
        inx
        ldy #0
:       lda load_table,x
        sta param_address,y
        inx
        iny
        cpy #7
        bne :-
        txa
        pha
.if DISKS
        jsr load_staged
.else
        jsr disk_read
.endif
        pla
        tax
        cpx #LOADS * 8
        bne @load

        ; Checked startup snapshot: $E000-$FF49 is entirely zero. OS is out;
        ; recreate these bytes exactly without 63 disk-sector reads. Stop
        ; before the stand-in registers at $FF50 and the vectors at $FFFA.
        lda #0
        ldy #0
        ldx #$1F
zero_page:
zero_target = * + 2
:       sta $E000,y
        iny
        bne :-
        inc zero_target
        dex
        bne zero_page
:       sta $FF00,y
        iny
        cpy #$4A
        bne :-

        sei                     ; memory the game expects as the C64 left it
        ldx #2
:       lda image_zero,x
        sta $00,x
        inx
        bne :-
        ldx #0
:       lda image_page2,x       ; $028A-$0291
        sta $028A,x
        inx
        cpx #8
        bne :-
        ldx #0
:       lda image_page3,x       ; $0334-$03FF
        sta $0334,x
        inx
        cpx #$CC
        bne :-
        ldx #0
:       lda image_low,x         ; $0400-$0AFF
        sta $0400,x
        lda image_low+$100,x
        sta $0500,x
        lda image_low+$200,x
        sta $0600,x
        lda image_low+$300,x
        sta $0700,x
        lda image_low+$400,x
        sta $0800,x
        lda image_low+$500,x
        sta $0900,x
        lda image_low+$600,x
        sta $0A00,x
        inx
        bne :-
        ldx #6                  ; the rest of memory is under this code: the
                                ; kernel loads it and enters the game
:       lda last_load+1,x
        sta param_address,x
        dex
        bpl :-
        lda last_load
        sta side
.if DISKS .or XE64
        ldx #enter_stub_end - enter_stub - 1    ; the last load covers this code: finish from the stack page
:       lda enter_stub,x
        sta $0180,x
        dex
        bpl :-
        jmp $0180
.else
        jmp enter_game
.endif

; Read the piece described by the 8 bytes at load_now: side, then the game's
; seven disk parameters.
load:   lda load_now
        sta side
        ldx #6
:       lda load_now+1,x
        sta param_address,x
        dex
        bpl :-
        jmp disk_read
load_now:       .res 8

.if DISKS
; The OS ROM is in while the kernel unpacks, and hides what a load writes to
; $C000 and above. Such a piece is read to STAGE, and copied here with the ROM
; out.
STAGE = $4000
load_staged:
        clc
        lda param_address
        adc param_length
        lda param_address+1
        adc param_length+1
        cmp #$C0
        bcc @plain
        lda param_address       ; where it belongs, in $F0/$F1
        sta $F0
        lda param_address+1
        sta $F1
        lda #<STAGE
        sta $F2
        sta param_address
        lda #>STAGE
        sta $F3
        sta param_address+1
        jsr disk_read
        ldx param_length+1      ; whole pages
        beq @rest
@page:  ldy #0
:       lda ($F2),y
        sta ($F0),y
        iny
        bne :-
        inc $F3
        inc $F1
        dex
        bne @page
@rest:  ldy #0
        cpy param_length
        beq @done
:       lda ($F2),y
        sta ($F0),y
        iny
        cpy param_length
        bne :-
@done:  rts
@plain: jmp disk_read
.endif

.if DISKS .or XE64
; Last step of the boot, run from $0180 (nothing loaded reaches the stack page):
; load the piece of memory this code was in, then enter the game with the
; registers the C64 has at this point.
enter_stub:
        jsr disk_read
        .if !DISKS
        lda #0
        sta side
        .endif
        ldx #START_S
        txs
        lda #START_P
        pha
        lda #START_A
        ldx #START_X
        ldy #START_Y
        plp
        jmp GAME_START
enter_stub_end:
.endif

load_table:
        .include "loads.inc"

image_loader:   .incbin "loader.bin"
image_under:    .incbin "under.bin"
image_top:      .incbin "top.bin"
.if !XE64
image_ext:      .incbin "ext.bin"
.endif
image_zero:     .incbin "zero.bin"      ; $0000-$00FF at the stub's entry
image_page2:    .incbin "page2.bin"
image_page3:    .incbin "page3.bin"
image_low:      .incbin "low.bin"
