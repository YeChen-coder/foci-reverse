[中文](#中文) · [English](#english)

# 中文

具体的部署和技术细节，请去看 [SETUP.md](SETUP.md)。

这边就是单纯由作者来讲一下，这个项目是为了个什么的。这是一个蓝牙逆向的项目，是对一个叫 FOCI 的 IoT 设备做的蓝牙逆向。

这个 FOCI 我估计还是挺小众的一个东西，2018 年发布的。现在它的官网好像都没了，更不用提销售了。（厂家请别告我，我真诚的喜欢这个设备来的）

如果大家对这个感兴趣，想了解更多信息，这篇文章其实介绍得都挺好的了：https://www.jumpstartmag.com/product-review-foci-ai/

作者就是单纯在这里稍微吐槽一下哈。

<img width="479" height="372" alt="image" src="https://github.com/user-attachments/assets/a0e097a0-2837-4b37-836b-e46d25933db2" />

简单来说，这个东西是一个别在裤腰带上的设备。它通过内置的传感器监测呼吸频率，从而判断用户当前的精神状况（比如是不是累了，或者是不是分心了）。

它的底层原理是：先根据用户大概一周的日常观察数据，进行 Machine learning（机器学习）训练，然后再根据训练结果，为用户做一些定制化的监测。

这个设备其实用下来我觉得还是挺好的：它很优雅，手机 App 的界面也是非常之好看。虽然功能确实单一了一点，但这并不会影响它在作者心中的喜爱程度。

大家得想一下，虽然现在的手环以及其他可穿戴设备都能检测身体状况，像睡眠、心跳、脉搏等等都能测，但你得考虑一下：这个设备是 2018 年出来的东西。Take this into consideration，它已经是一个很优雅的设备了。

我不会说它是一个在销售上成功的设备，但它肯定是一个非常 elegant 的，很有设计感的东西。

但是还是有一点我非常想吐槽：如果想要实时查看自己的状态，就需要打开手机 App。那么这个功能的设计者有没有考虑过，手机本身其实就是一个让人分心的危险源？

正如在很多领域一样，人们渐渐发现，面对问题时最根本的思路，应该是设计一个环境，让人不需要这么好，而不是试图让人变得更好。那么在需要专心减少干扰的环境中，有没有可能手机本身最好就不要存在？

话题扯远了，但我说这个，其实就扯到了为什么要对它进行网页端移植（让大家能在网页上看到蓝牙实时传过来的数据）。

虽然讲道理，手机 App 的页面比我搞的这个基础网页好看太多了，作者强烈推荐使用者使用手机 App。

但是，我之所以把它放在网页上，其中一大原因就是为了让手机离开——一开始就不要碰手机。不碰手机，自然就远离了斜坡。

抱歉确实扯远了。回来谈正事，下图是网页端的截图，基本上把手机 App 那边能搞的功能全复制过来了，用的是电脑自带的蓝牙去跟设备连接。

至于提示方式这些，不管是在手机 App 还是在网页端上，其实都只能选择打不打开 notification。但具体是什么样的 notification、表现成什么样（比如短震几下、长震一下），这些都是写在设备内部的，本来就改不了。其他的一些 signal 也是设备直接集成在里面自己传出来的，确实没办法拿到更原始的数据了。

请注意一下，就是它那个手机 App 上能出的 Deep Work 报告，这边是出不来的，不过也无伤大雅就是了。

<img width="1109" height="726" alt="image" src="https://github.com/user-attachments/assets/a2c6b56e-f82b-4807-ba03-132e940640ee" />

实时运行的时候是这样的，能显示数值：

<img width="1128" height="581" alt="image" src="https://github.com/user-attachments/assets/37e66e13-1c05-48fc-ab97-d98003afd81f" />

这个设备确实很坚挺。它是 2018 年初出的，我大概是 2020 年的时候去买的，都六年了它还能正常工作，不得不让人感叹这个设计真的很好。

而且这个设计哪怕放在今天，就这么一个极简的外形，以及那么美貌的 App 页面，真的很好。不过，也许它注定就是一个小众一点的设备吧。

THE END

---

# English

For installation instructions and technical details, please see [SETUP.md](SETUP.md).

This section is simply the author explaining what this project is about. It is a Bluetooth reverse-engineering project for an IoT device called FOCI.

FOCI was already a fairly niche product when it was released in 2018. Its official website now appears to be gone, never mind any way to buy one. (Please do not sue me, dear manufacturer—I genuinely love this device.)

If you are interested and would like to learn more about it, this article provides a pretty good introduction: https://www.jumpstartmag.com/product-review-foci-ai/

The author is mostly here to ramble and complain a little.

<img width="479" height="372" alt="image" src="https://github.com/user-attachments/assets/a0e097a0-2837-4b37-836b-e46d25933db2" />

In simple terms, FOCI is a small device that clips onto your waistband. It uses its built-in sensors to monitor your breathing rate and infer your current mental state—for example, whether you are tired or distracted.

The basic idea is that it first collects roughly a week of everyday observations for machine-learning training, then uses the resulting model to provide monitoring tailored to the individual user.

In actual use, I think it is a very good device. It is elegant, and the mobile App has a genuinely beautiful interface. Its feature set is admittedly rather narrow, but that does not make me like it any less.

It is worth remembering that although today's fitness bands and other wearables routinely track sleep, heart rate, pulse, and all sorts of physical signals, this device came out in 2018. Take that into consideration, and it really was an elegant product.

I would not call it a commercial success, but it was certainly an elegant and thoughtfully designed object.

There is, however, one thing I very much want to complain about: if you want to view your state in real time, you have to open the mobile App. Did the designers of that feature consider that the phone itself might be one of the most dangerous sources of distraction?

As people have gradually discovered in many other fields, the most fundamental way to address a problem is often to design an environment that demands less virtue from us, rather than trying to make people better at resisting temptation. In an environment meant for concentration and reduced distraction, might it be better for the phone not to be present at all?

That is a bit of a tangent, but it leads directly to why I ported the experience to a web interface: so that the Bluetooth data can be viewed in real time on a computer.

To be fair, the mobile App looks far better than the basic web page I built here. The author strongly recommends using the mobile App whenever that fits your needs.

One major reason for putting it on the web, however, is precisely to remove the phone from the situation—to avoid touching it in the first place. If you never pick up the phone, you never step onto that slippery slope.

Sorry for the long detour. Back to the project: the screenshot below shows the web interface. It reproduces most of the functions available in the mobile App and uses the computer's built-in Bluetooth hardware to connect directly to the device.

As for alert patterns, both the mobile App and the web interface can only enable or disable each notification category. The actual form of an alert—several short vibrations, one long vibration, and so on—is built into the device and cannot normally be changed. The other signal values are also processed inside the device and transmitted directly, so there does not appear to be a way to obtain more primitive raw sensor data.

One limitation worth noting is that the web version cannot generate the Deep Work reports available in the mobile App. In practice, that is not a major loss.

<img width="1109" height="726" alt="image" src="https://github.com/user-attachments/assets/a2c6b56e-f82b-4807-ba03-132e940640ee" />

This is what the interface looks like while running, with the live values displayed:

<img width="1128" height="581" alt="image" src="https://github.com/user-attachments/assets/37e66e13-1c05-48fc-ab97-d98003afd81f" />

The device has proved remarkably durable. It was released in early 2018, and I bought mine around 2020. Six years later, it still works normally, which says a great deal about the quality of the design.

Even today, its minimalist form and beautiful App interface still hold up extremely well. Perhaps it was simply destined to remain a niche device.

THE END
