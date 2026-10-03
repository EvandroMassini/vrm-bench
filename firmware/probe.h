/* Address-only probe. Open-drain GPIO: never drive a high level.
 * SDK hardware I2C cannot send a zero-length write. Single-master bench use only.
 * Sampling idle/arbitration does NOT make this a multi-master implementation.
 */
static void release_pin(unsigned pin) { gpio_set_dir(pin, GPIO_IN); }
static void low_pin(unsigned pin) { gpio_put(pin, 0); gpio_set_dir(pin, GPIO_OUT); }
static bool raise_clock(void) {
    release_pin(SCL_PIN);
    absolute_time_t deadline = make_timeout_time_us(TIMEOUT_US);
    while (!gpio_get(SCL_PIN)) {
        if (time_reached(deadline)) return false;
        tight_loop_contents();
    }
    sleep_us(half_period_us);
    return true;
}
static const char *probe_address(unsigned address) {
    i2c_deinit(i2c0);
    gpio_init(SDA_PIN);
    gpio_init(SCL_PIN);
    gpio_disable_pulls(SDA_PIN);
    gpio_disable_pulls(SCL_PIN);
    release_pin(SDA_PIN);
    release_pin(SCL_PIN);
    const char *result = "ERR BUS_BUSY";
    /* Reject activity/low lines observed during a 1ms idle window. */
    for (int i=0; i<100; ++i) {
        if (!gpio_get(SDA_PIN) || !gpio_get(SCL_PIN)) goto finish;
        sleep_us(10);
    }
    low_pin(SDA_PIN); /* START */
    sleep_us(half_period_us);
    low_pin(SCL_PIN);
    for (int bit=7; bit>=0; --bit) {
        bool one = (((address << 1) >> bit) & 1u) != 0;
        if (one) release_pin(SDA_PIN); else low_pin(SDA_PIN);
        sleep_us(half_period_us);
        if (!raise_clock()) { result="ERR SCL_TIMEOUT"; goto finish; }
        if (one && !gpio_get(SDA_PIN)) { result="ERR BUS_CONFLICT"; goto finish; }
        low_pin(SCL_PIN);
    }
    release_pin(SDA_PIN);
    sleep_us(half_period_us);
    if (!raise_clock()) { result="ERR SCL_TIMEOUT"; goto finish; }
    result = gpio_get(SDA_PIN) ? "OK NACK" : "OK ACK";
    low_pin(SCL_PIN);
    low_pin(SDA_PIN);
    sleep_us(half_period_us);
    if (!raise_clock()) { result="ERR SCL_TIMEOUT"; goto finish; }
    release_pin(SDA_PIN); /* STOP, no register or data byte */
    sleep_us(half_period_us);
    if (!gpio_get(SDA_PIN)) result="ERR BUS_BUSY";
finish:
    release_pin(SDA_PIN);
    release_pin(SCL_PIN);
    bus_init();
    return result;
}
